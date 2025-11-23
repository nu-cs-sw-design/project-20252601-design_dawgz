"""
Filename: image_generation_routes.py
Description: Routes for generating questions from images.
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
from models import UnifiedQuestioSingleItem, ExtractedQuestion
from ...utils.class_info import get_class_info
from ...utils.db_operations import fetch_next_order_number

# Load config.yaml
config_path = os.path.join(os.path.dirname(__file__), "../../utils/config.yaml")
with open(config_path, "r", encoding="utf-8") as f:
    config = yaml.safe_load(f)




@gpt_bp.route("/generate_from_image", methods=["POST", "OPTIONS"])
def generate_from_image():
    """
    Generate multiple structured questions from an image using GPT-4o vision.
    Accepts image file, user metadata, number of questions to generate, and optional order number.
    """
    if request.method == "OPTIONS":
        response = make_response("", 200)
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        return response

    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    print("Generating questions from image...")

    file = request.files["file"]
    userid = request.form.get("userid")
    classid = request.form.get("classid")
    test_id = request.form.get("test_id")
    num_mcq = request.form.get("num_mcq", 0)
    num_frq = request.form.get("num_frq", 0)
    order_number = request.form.get("order_number")
    image_description = request.form.get("image_description", "")
    print("Image Desciription: " + str(image_description))

    info = get_class_info(userid, classid)
    classname = info["class_id"]
    classdesc = info["class_description"]

    if not all([userid, classid, test_id]):
        return jsonify({"error": "Missing required form data"}), 400

    try:
        num_mcq = int(num_mcq)
        num_frq = int(num_frq)
    except ValueError:
        return jsonify({"error": "Invalid number format for num_mcq or num_frq"}), 400

    if order_number is not None:
        try:
            order_number = int(order_number)
        except ValueError:
            return jsonify({"error": "Invalid order number format"}), 400

    # Process image
    img_bytes = file.read()
    img_base64 = base64.b64encode(img_bytes).decode("utf-8")
    image_url = f"data:image/png;base64,{img_base64}"

    client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    prompt_text = config["prompts"]["image_question_conversion"]
    generated_items = []
    existing_questions = []

    # Loop for number of questions requested
    for i in range(num_mcq + num_frq):
        question_type = "MC" if i < num_mcq else "FR"

        try:

            rendered_prompt = config["prompts"]["image_generation_looped"].format(
                class_name=classid,
                class_description=classdesc,
                image_description=image_description,
                existing_questions=json.dumps(existing_questions),
                question_type=question_type,
            )
            response = client.responses.parse(
                model=config["gpt_model"]["engine"],
                input=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "input_text",
                                "text": rendered_prompt,
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
            if result.questions:
                item = result.questions[0]
                item.item_id = f"{test_id}_{str(uuid.uuid4())[:12]}"
                generated_items.append(item)
                existing_questions.append(item.question_part)

        except Exception as e:
            print(f"Error generating question {i+1}: {e}")
            continue

    inserted_items = []
    highest_topic_result = db.session.execute(
        text(
            "SELECT topic_id FROM item_topics WHERE user_id = :user_id AND class_id = :class_id ORDER BY topic_id DESC LIMIT 1"
        ),
        {"user_id": userid, "class_id": classid},
    ).fetchone()

    highest_skill_result = db.session.execute(
        text(
            "SELECT skill_id FROM item_skills WHERE user_id = :user_id AND class_id = :class_id ORDER BY skill_id DESC LIMIT 1"
        ),
        {"user_id": userid, "class_id": classid},
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
    total_questions = num_mcq + num_frq

    if order_number is not None:
        fetch_next_order_number(
            db.session, userid, classid, test_id, order_number, total_questions
        )

    try:
        for idx, item_response in enumerate(generated_items):
            question_type = item_response.format
            question = item_response.question_part
            difficulty = item_response.difficulty
            wrong_answer_explanation = item_response.wrong_answer_explanation
            item_id = item_response.item_id

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
                    "user_id": userid,
                    "class_id": classid,
                    "item_id": item_id,
                    "version": version,
                },
            )

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
                    """INSERT INTO item_history 
                    (user_id, class_id, item_id, version, question_part, answer_part, format, difficulty, wrong_answer_explanation)
                    VALUES (:user_id, :class_id, :item_id, :version, :question_part, :answer_part, :format, :difficulty, :wrong_answer_explanation)"""
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
                    "wrong_answer_explanation": wrong_answer_explanation,
                },
            )

            if idx == 0 and order_number is not None:
                current_order = order_number
            elif order_number is not None:
                current_order = order_number + idx
            else:
                current_order = fetch_next_order_number(
                    db.session, userid, classid, test_id
                )

            db.session.execute(
                text(
                    """INSERT INTO tests 
                    (user_id, class_id, test_id, item_id, order_number)
                    VALUES (:user_id, :class_id, :test_id, :item_id, :order_number)"""
                ),
                {
                    "user_id": userid,
                    "class_id": classid,
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
                        "user_id": userid,
                        "class_id": classid,
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
                        "user_id": userid,
                        "class_id": classid,
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
                    "message": f"{len(inserted_items)} topic-format questions processed and inserted.",
                    "items": inserted_items,
                }
            ),
            200,
        )

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "Failed to insert questions", "detail": str(e)}), 500