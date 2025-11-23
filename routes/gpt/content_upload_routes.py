"""
Filename: content_upload_routes.py
Description: Routes for processing syllabus and PDF uploads.
"""

from flask import jsonify, request, make_response
from .gpt_blueprint import gpt_bp
from sqlalchemy import text
from app import db
import openai
import os
import json
import uuid
import yaml
from PIL import Image
import base64
from io import BytesIO
from pdf2image import convert_from_bytes
from models import ExtractedQuestion
from ...utils.class_info import get_class_info
from ...utils.db_operations import fetch_next_order_number
from ...utils.testconvert import normalize_pdf_images_to_summary
from werkzeug.utils import secure_filename

# Load config.yaml
config_path = os.path.join(os.path.dirname(__file__), "../../utils/config.yaml")
with open(config_path, "r", encoding="utf-8") as f:
    config = yaml.safe_load(f)



@gpt_bp.route("/process_syllabus", methods=["POST"])
def process_syllabus():
    """
    Upload a syllabus PDF, extract and summarize text using GPT-4 Vision, then generate questions.
    """

    # Basic file + metadata checks
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    files = request.files.getlist("file")
    user_id = request.form.get("user_id")
    class_id = request.form.get("class_id")
    test_topic = request.form.get(
        "test_topic"
    )  # for some reason this is the user input
    test_id = request.form.get("test_id")
    num_mcq = request.form.get("num_mcq")
    num_frq = request.form.get("num_frq")
    order_number = request.form.get("order_number")

    if not all([user_id, class_id, test_topic, test_id, num_mcq, num_frq]):
        return jsonify({"error": "Missing required form data"}), 400

    print("Processing syllabus...")

    info = get_class_info(user_id, class_id)
    classdesc = info["class_description"]

    try:
        num_mcq = int(num_mcq)
        num_frq = int(num_frq)
        if order_number is not None:
            order_number = int(order_number)
    except ValueError:
        return (
            jsonify(
                {"error": "Invalid number format for num_mcq, num_frq, or order_number"}
            ),
            400,
        )

    client = openai.OpenAI()

    full_text = ""
    images = []

    if len(files) == 1 and files[0].filename.lower().endswith(".pdf"):
        try:
            files[0].seek(0)
            images = convert_from_bytes(files[0].read())
        except Exception as e:
            return jsonify({"error": f"Failed to convert PDF to images: {str(e)}"}), 500
    else:
        try:
            for f in files:
                img = Image.open(f.stream).convert("RGB")
                images.append(img)
        except Exception as e:
            return jsonify({"error": f"Failed to read images: {str(e)}"}), 500

    for i, img in enumerate(images):
        buffered = BytesIO()
        img.save(buffered, format="PNG")
        img_base64 = base64.b64encode(buffered.getvalue()).decode("utf-8")
        image_url = f"data:image/png;base64,{img_base64}"

        try:
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": "You are an assistant that extracts all readable text from images of curriculum guides. Extract text from this page of a curriculum guide. Do not make up content. If the text is logistic related and not academically related and not centered around the curriculum do not include it. Preserve formatting when helpful.",
                            },
                            {"type": "image_url", "image_url": {"url": image_url}},
                        ],
                    },
                ],
            )
            page_text = response.choices[0].message.content
            full_text += f"\n\n--- Page {i+1} ---\n\n" + page_text
        except Exception as e:
            print(f"Failed to process image {i + 1}: {e}")
            continue

    prompt_template = config["prompts"]["syllabus_single_question_generation_looped"]

    generated = []
    existing_questions = []
    for i in range(num_mcq + num_frq):
        question_type = "MC" if i < num_mcq else "FR"
        rendered_prompt = prompt_template.format(
            class_name=class_id,
            class_description=classdesc,
            user_info=test_topic,
            syllabus_text=full_text,
            existing_questions=json.dumps(existing_questions),
            question_type=question_type,
        )

        try:
            response = client.responses.parse(
                model=config["gpt_model"]["engine"],
                input=rendered_prompt,
                text_format=ExtractedQuestion,
                reasoning={"effort": config["gpt_model"]["reasoning"]},
                text={"verbosity": config["gpt_model"]["verbosity"]},
            )

            result = response.output[1].content[0].parsed
            if result.questions:
                item = result.questions[0]
                item.item_id = str(uuid.uuid4())
                generated.append(item)
                existing_questions.append(item.question_part)

        except Exception as e:
            print(f"Error generating question {i+1}: {e}")
            continue

    inserted_items = []

    highest_topic_result = db.session.execute(
        text(
            "SELECT topic_id FROM item_topics WHERE user_id = :user_id AND class_id = :class_id ORDER BY topic_id DESC LIMIT 1"
        ),
        {"user_id": user_id, "class_id": class_id},
    ).fetchone()

    highest_skill_result = db.session.execute(
        text(
            "SELECT skill_id FROM item_skills WHERE user_id = :user_id AND class_id = :class_id ORDER BY skill_id DESC LIMIT 1"
        ),
        {"user_id": user_id, "class_id": class_id},
    ).fetchone()

    def get_next_id(current_id, prefix):
        if not current_id:
            return f"{prefix}_0"
        try:
            num = int(current_id.split("_")[1])
            return f"{prefix}_{num + 1}"
        except (IndexError, ValueError):
            return f"{prefix}_0"

    current_topic_id = get_next_id(
        highest_topic_result[0] if highest_topic_result else None, "topic"
    )
    current_skill_id = get_next_id(
        highest_skill_result[0] if highest_skill_result else None, "skill"
    )

    version = 0

    if order_number is not None:
        fetch_next_order_number(
            db.session, user_id, class_id, test_id, order_number, num_mcq + num_frq
        )

    try:
        for idx, item_response in enumerate(generated):
            question_type = item_response.format
            question = item_response.question_part
            difficulty = item_response.difficulty
            wrong_answer_explanation = item_response.wrong_answer_explanation
            item_id = f"{test_id}_{str(uuid.uuid4())[:12]}"

            if question_type == "MC":
                answer_part = json.dumps(
                    {
                        "A": item_response.answer_part.A,
                        "B": item_response.answer_part.B,
                        "C": item_response.answer_part.C,
                        "D": item_response.answer_part.D,
                        "Correct": item_response.answer_part.Correct,
                    }
                )
            else:
                answer_part = item_response.answer_part

            db.session.execute(
                text(
                    "INSERT INTO item_current (user_id, class_id, item_id, version) VALUES (:user_id, :class_id, :item_id, :version)"
                ),
                {
                    "user_id": user_id,
                    "class_id": class_id,
                    "item_id": item_id,
                    "version": version,
                },
            )

            existing_class = db.session.execute(
                text(
                    "SELECT 1 FROM user_classes WHERE user_id = :user_id AND class_id = :class_id"
                ),
                {"user_id": user_id, "class_id": class_id},
            ).fetchone()
            if not existing_class:
                db.session.execute(
                    text(
                        "INSERT INTO user_classes (user_id, class_id) VALUES (:user_id, :class_id)"
                    ),
                    {"user_id": user_id, "class_id": class_id},
                )

            db.session.execute(
                text(
                    """INSERT INTO item_history 
                    (user_id, class_id, item_id, version, question_part, answer_part, format, difficulty, wrong_answer_explanation)
                    VALUES (:user_id, :class_id, :item_id, :version, :question_part, :answer_part, :format, :difficulty, :wrong_answer_explanation)"""
                ),
                {
                    "user_id": user_id,
                    "class_id": class_id,
                    "item_id": item_id,
                    "version": version,
                    "question_part": question,
                    "answer_part": answer_part,
                    "format": question_type,
                    "difficulty": difficulty,
                    "wrong_answer_explanation": wrong_answer_explanation,
                },
            )

            if idx == 0 and order_number is not None:
                current_order = order_number
            elif order_number is not None:
                current_order = order_number + idx
            else:
                current_order = fetch_next_order_number(
                    db.session, user_id, class_id, test_id
                )

            db.session.execute(
                text(
                    """INSERT INTO tests 
                    (user_id, class_id, test_id, item_id, order_number)
                    VALUES (:user_id, :class_id, :test_id, :item_id, :order_number)"""
                ),
                {
                    "user_id": user_id,
                    "class_id": class_id,
                    "test_id": test_id,
                    "item_id": item_id,
                    "order_number": current_order,
                },
            )

            for topic_name in item_response.relatedtopics:
                topic_id = get_next_id(current_topic_id, "topic")
                current_topic_id = topic_id
                db.session.execute(
                    text(
                        """INSERT INTO item_topics 
                        (user_id, class_id, item_id, version, topic_id, topic_name)
                        VALUES (:user_id, :class_id, :item_id, :version, :topic_id, :topic_name)"""
                    ),
                    {
                        "user_id": user_id,
                        "class_id": class_id,
                        "item_id": item_id,
                        "version": version,
                        "topic_id": topic_id,
                        "topic_name": topic_name,
                    },
                )

            for skill_name in item_response.relatedskills:
                skill_id = get_next_id(current_skill_id, "skill")
                current_skill_id = skill_id
                db.session.execute(
                    text(
                        """INSERT INTO item_skills 
                        (user_id, class_id, item_id, version, skill_id, skill_name)
                        VALUES (:user_id, :class_id, :item_id, :version, :skill_id, :skill_name)"""
                    ),
                    {
                        "user_id": user_id,
                        "class_id": class_id,
                        "item_id": item_id,
                        "version": version,
                        "skill_id": skill_id,
                        "skill_name": skill_name,
                    },
                )

            inserted_items.append(
                {
                    "item_id": item_id,
                    "question": question,
                    "answer_part": answer_part,
                    "format": question_type,
                    "difficulty": difficulty,
                    "wrong_answer_explanation": wrong_answer_explanation,
                    "order_number": current_order,
                }
            )

        db.session.commit()
        return (
            jsonify(
                {
                    "message": f"{len(inserted_items)} syllabus questions processed and inserted.",
                    "items": inserted_items,
                }
            ),
            200,
        )

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "Failed to insert questions", "detail": str(e)}), 500

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "Failed to insert questions", "detail": str(e)}), 500


@gpt_bp.route("/pdf_upload", methods=["POST"])
def pdf_upload():
    userid = request.form.get("userid")
    classid = request.form.get("classid")
    test_id = request.form.get("test_id")
    order_number = request.form.get("order_number")

    if not userid or not classid or not test_id:
        return jsonify({"error": "Missing form data"}), 400

    print("Uploading PDF or images...")

    if order_number is not None:
        try:
            order_number = int(order_number)
        except ValueError:
            return jsonify({"error": "Invalid order number format"}), 400

    files = request.files.getlist("files")
    if not files or len(files) == 0:
        return jsonify({"error": "No file(s) uploaded"}), 400

    # Determine file types
    is_pdf = len(files) == 1 and files[0].filename.lower().endswith(".pdf")
    is_images = all(f.mimetype.startswith("image/") for f in files)

    if not (is_pdf or is_images):
        return (
            jsonify(
                {
                    "error": "Invalid file types. Upload a single PDF/DOCX or multiple images."
                }
            ),
            400,
        )

    if is_images:
        print(f"Received {len(files)} image(s)")
        all_questions = []
        client = openai.OpenAI()
        for idx, img_file in enumerate(files):
            img = Image.open(img_file.stream).convert("RGB")
            buffered = BytesIO()
            img.save(buffered, format="PNG")
            img_base64 = base64.b64encode(buffered.getvalue()).decode("utf-8")
            image_url = f"data:image/png;base64,{img_base64}"

            try:
                response = client.responses.parse(
                    model=config["gpt_model"]["engine"],
                    input=[
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "input_text",
                                    "text": config["prompts"]["pdf_conversion"],
                                },
                                {
                                    "type": "input_image",
                                    "image_url": image_url,
                                }
                            ]
                        }
                    ],
                    text_format=ExtractedQuestion,
                    reasoning={"effort": config["gpt_model"]["reasoning"]},
                    text={"verbosity": config["gpt_model"]["verbosity"]},
                )
                result = response.output[1].content[0].parsed
                questions = result.questions
                all_questions.extend(questions)
            except Exception as e:
                print(f"Error processing image {idx+1}: {e}")
                continue

    else:
        file = files[0]
        filename = secure_filename(file.filename)
        print(f"Received file: {filename}")
        try:
            all_questions = normalize_pdf_images_to_summary(file)
        except Exception as e:
            return jsonify({"error": f"Failed to parse file: {str(e)}"}), 500

    total_questions = len(all_questions)

    # Get next topic/skill IDs
    def get_next_id(current_id, prefix):
        if not current_id:
            return f"{prefix}_0"
        try:
            num = int(current_id.split("_")[1])
            return f"{prefix}_{num + 1}"
        except (IndexError, ValueError):
            return f"{prefix}_0"

    highest_topic_result = db.session.execute(
        text(
            """
            SELECT topic_id FROM item_topics
            WHERE user_id = :user_id AND class_id = :class_id
            ORDER BY topic_id DESC LIMIT 1
        """
        ),
        {"user_id": userid, "class_id": classid},
    ).fetchone()

    highest_skill_result = db.session.execute(
        text(
            """
            SELECT skill_id FROM item_skills
            WHERE user_id = :user_id AND class_id = :class_id
            ORDER BY skill_id DESC LIMIT 1
        """
        ),
        {"user_id": userid, "class_id": classid},
    ).fetchone()

    current_topic_id = get_next_id(
        highest_topic_result[0] if highest_topic_result else None, "topic"
    )
    current_skill_id = get_next_id(
        highest_skill_result[0] if highest_skill_result else None, "skill"
    )
    version = 0

    if order_number is not None:
        fetch_next_order_number(
            db.session, userid, classid, test_id, order_number, total_questions
        )

    for i, item in enumerate(all_questions):
        question_type = item.format
        question = item.question_part
        difficulty = item.difficulty
        wrong_answer_explanation = item.wrong_answer_explanation or ""
        item_id = f"{test_id}_{str(uuid.uuid4())[:12]}"

        if question_type == "MC":
            answer_part = json.dumps(
                {
                    "A": item.answer_part.A,
                    "B": item.answer_part.B,
                    "C": item.answer_part.C,
                    "D": item.answer_part.D,
                    "Correct": item.answer_part.Correct,
                }
            )
        else:
            answer_part = item.answer_part

        try:
            existing_class = db.session.execute(
                text(
                    "SELECT 1 FROM user_classes WHERE user_id = :user_id AND class_id = :class_id"
                ),
                {"user_id": userid, "class_id": classid},
            ).fetchone()
            if not existing_class:
                db.session.execute(
                    text(
                        "INSERT INTO user_classes (user_id, class_id) VALUES (:user_id, :class_id)"
                    ),
                    {"user_id": userid, "class_id": classid},
                )
                
            db.session.execute(
                text(
                    """
                INSERT INTO item_current (user_id, class_id, item_id, version)
                VALUES (:user_id, :class_id, :item_id, :version)
            """
                ),
                {
                    "user_id": userid,
                    "class_id": classid,
                    "item_id": item_id,
                    "version": version,
                },
            )

            

            db.session.execute(
                text(
                    """
                INSERT INTO item_history
                (user_id, class_id, item_id, version, question_part, answer_part, format, difficulty, wrong_answer_explanation)
                VALUES (:user_id, :class_id, :item_id, :version, :question_part, :answer_part, :format, :difficulty, :explanation)
            """
                ),
                {
                    "user_id": userid,
                    "class_id": classid,
                    "item_id": item_id,
                    "version": version,
                    "question_part": question,
                    "answer_part": answer_part,
                    "format": question_type,
                    "difficulty": difficulty,
                    "explanation": wrong_answer_explanation,
                },
            )

            if i == 0 and order_number is not None:
                current_order = order_number
            elif order_number is not None:
                current_order = order_number + i
            else:
                current_order = fetch_next_order_number(
                    db.session, userid, classid, test_id
                )

            db.session.execute(
                text(
                    """
                INSERT INTO tests (user_id, class_id, test_id, item_id, order_number)
                VALUES (:user_id, :class_id, :testid, :item_id, :order_number)
            """
                ),
                {
                    "user_id": userid,
                    "class_id": classid,
                    "testid": test_id,
                    "item_id": item_id,
                    "order_number": current_order,
                },
            )

            for topic_name in item.relatedtopics:
                topic_id = get_next_id(current_topic_id, "topic")
                current_topic_id = topic_id
                db.session.execute(
                    text(
                        """
                    INSERT INTO item_topics (user_id, class_id, item_id, version, topic_id, topic_name)
                    VALUES (:user_id, :class_id, :item_id, :version, :topic_id, :topic_name)
                """
                    ),
                    {
                        "user_id": userid,
                        "class_id": classid,
                        "item_id": item_id,
                        "version": version,
                        "topic_id": topic_id,
                        "topic_name": topic_name,
                    },
                )

            for skill_name in item.relatedskills:
                skill_id = get_next_id(current_skill_id, "skill")
                current_skill_id = skill_id
                db.session.execute(
                    text(
                        """
                    INSERT INTO item_skills (user_id, class_id, item_id, version, skill_id, skill_name)
                    VALUES (:user_id, :class_id, :item_id, :version, :skill_id, :skill_name)
                """
                    ),
                    {
                        "user_id": userid,
                        "class_id": classid,
                        "item_id": item_id,
                        "version": version,
                        "skill_id": skill_id,
                        "skill_name": skill_name,
                    },
                )

            db.session.commit()

        except Exception as e:
            db.session.rollback()
            print(f"Error inserting item {i+1}: {e}")
            continue

    return (
        jsonify({"message": "All questions added successfully.", "test_id": test_id}),
        200,
    )