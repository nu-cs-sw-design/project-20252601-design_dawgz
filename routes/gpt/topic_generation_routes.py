"""
Filename: topic_generation_routes.py
Description: Routes for generating questions based on topics and formats.
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
from models import ExtractedQuestion
from ...utils.class_info import get_class_info
from ...utils.db_operations import fetch_next_order_number


@gpt_bp.route("/generate_multiple_items", methods=["POST", "OPTIONS"])
def generate_multiple_items():
    """
    Generates multiple items (MC or FR) for the specified class using the GPT API.

    Expects JSON with:
        userid (str): User ID
        classid (str): Class ID
        testid (str): Test ID
        type (str): Question type ("mc" or "fr")
        topic (str): Topic for the question
        orderNumber (int, optional): Position to insert the new items

    Returns:
        JSON response containing the generated items as an array.
    """
    # Handle CORS OPTIONS request
    if request.method == "OPTIONS":
        response = make_response("", 200)
        response.headers["Access-Control-Allow-Origin"] = (
            request.headers.get("Origin") or "*"
        )
        response.headers["Vary"] = "Origin"
        response.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        return response

    print("Generating multiple items...")

    form = request.form
    userid = form.get("userid")
    classid = form.get("classid")
    testid = form.get("testid")
    topics_raw = form.get("topics")
    order_number = form.get("order_number")

    print("topics: " + str(topics_raw))

    info = get_class_info(userid, classid)
    classdesc = info["class_description"]

    if order_number:
        try:
            order_number = int(order_number)
        except ValueError:
            return jsonify({"error": "order_number must be an integer"}), 400

    if not all([userid, classid, testid, topics_raw]):
        return jsonify({"error": "Missing required form data."}), 400

    try:
        topics_list = json.loads(topics_raw)
    except Exception as e:
        return jsonify({"error": f"Invalid topics format: {str(e)}"}), 400

    with open(
        os.path.join(os.path.dirname(__file__), "../../utils/config.yaml"),
        "r",
        encoding="utf-8",
    ) as f:
        config = yaml.safe_load(f)

    client = openai.OpenAI()
    generated_items = []

    # Count total questions to be generated
    total_questions = sum(
        entry.get("numMCQ", 0) + entry.get("numFRQ", 0) for entry in topics_list
    )

    # Build a comprehensive prompt for all questions at once
    topics_prompt = []
    for entry in topics_list:
        topic = entry.get("topic")
        num_mcq = entry.get("numMCQ", 0)
        num_frq = entry.get("numFRQ", 0)
        
        if num_mcq > 0:
            topics_prompt.append(f"- {num_mcq} multiple choice question(s) on {topic}")
        if num_frq > 0:
            topics_prompt.append(f"- {num_frq} free response question(s) on {topic}")
    
    topics_text = "\n".join(topics_prompt)
    
    # Single prompt for all questions
    prompt_template = config["prompts"]["topic_format_batch"]
    prompt = prompt_template.format(
        class_name=classid,
        class_description=classdesc,
        topic_name=topics_text,
    )

    try:
        # Make a single API call to generate all questions
        response = client.responses.parse(
            model=config["gpt_model"]["engine"],
            input=prompt,
            text_format=ExtractedQuestion,
            reasoning={"effort": config["gpt_model"]["reasoning"]},
            text={"verbosity": config["gpt_model"]["verbosity"]},
        )

        result = response.output[1].content[0].parsed
        
        if hasattr(result, 'questions'):
            if result.questions:
                # Assign unique IDs to all generated questions
                for i, item in enumerate(result.questions):
                    item.item_id = f"{testid}_{str(uuid.uuid4())[:12]}"
                    generated_items.append(item)
            else:
                print("Result.questions is empty or None")
            
    except Exception as e:
        return jsonify({"error": f"Failed to generate questions: {str(e)}"}), 500

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

    if order_number is not None:
        fetch_next_order_number(
            db.session, userid, classid, testid, order_number, total_questions
        )

    try:
        for idx, item_response in enumerate(generated_items):
            
            question_type = item_response.format
            question = item_response.question_part
            difficulty = item_response.difficulty
            wrong_answer_explanation = item_response.wrong_answer_explanation
            item_id = item_response.item_id
            
            # Truncate question if it's too long for database
            if len(question) > 1000:
                question = question[:997] + "..."

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

            # Get the appropriate order number
            if idx == 0 and order_number is not None:
                current_order = order_number
            elif order_number is not None:
                current_order = order_number + idx
            else:
                current_order = fetch_next_order_number(
                    db.session, userid, classid, testid
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
                    "test_id": testid,
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
        print(f"Error inserting questions: {str(e)}")
        return jsonify({"error": "Failed to insert questions", "detail": str(e)}), 500

