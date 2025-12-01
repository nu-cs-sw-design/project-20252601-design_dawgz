"""
Filename: similar_generation_routes.py
Description: Routes for generating similar questions.
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
from models import MultipleChoiceItem, FreeResponseItem, ExtractedQuestion
from ...utils.db_operations import (
    fetch_next_order_number, 
    fetch_highest_topic_id,
    fetch_highest_skill_id, 
    select_unique_class, 
    insert_item_current, 
    insert_item_history, 
    insert_tests,
    insert_item_topics,
    insert_item_skills
)

# Load config.yaml
config_path = os.path.join(os.path.dirname(__file__), "../../utils/config.yaml")
with open(config_path, "r", encoding="utf-8") as f:
    config = yaml.safe_load(f)



@gpt_bp.route("/generate_similar", methods=["POST", "OPTIONS"])
def generate_similar():
    # Handle CORS OPTIONS request
    if request.method == "OPTIONS":
        response = make_response("", 200)
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        return response

    data = request.get_json()
    if not data:
        return jsonify({"message": "No input data provided"}), 400

    print("Generating similar items...")

    userid = data.get("userId")
    classid = data.get("classId")
    testid = data.get("testId")
    question_type = data.get("type")  # "mc" or "fr"
    current_item = data.get("initialData")
    description = data.get("description")
    num_of_items = data.get("num_of_items", 1)
    order_number = data.get("orderNumber")

    try:
        num_of_items = int(num_of_items)
    except (ValueError, TypeError):
        num_of_items = 1

    if order_number is not None:
        try:
            order_number = int(order_number)
        except ValueError:
            return jsonify({"error": "orderNumber must be an integer"}), 400

    if not all([userid, classid, testid, question_type, current_item]):
        return jsonify({"message": "Missing required parameters"}), 400

    if not description:
        description = ""

    # Get the highest existing topic_id and skill_id
    highest_topic_result = fetch_highest_topic_id(db.session, userid, classid)
    # query_highest_topic = text(
    #     """
    #     SELECT topic_id FROM item_topics 
    #     WHERE user_id = :user_id AND class_id = :class_id
    #     ORDER BY topic_id DESC LIMIT 1
    # """
    # )
    # highest_topic_result = db.session.execute(
    #     query_highest_topic, {"user_id": userid, "class_id": classid}
    # ).fetchone()

    highest_skill_result = fetch_highest_skill_id(db.session, userid, classid)
    # query_highest_skill = text(
    #     """
    #     SELECT skill_id FROM item_skills 
    #     WHERE user_id = :user_id AND class_id = :class_id
    #     ORDER BY skill_id DESC LIMIT 1
    # """
    # )
    # highest_skill_result = db.session.execute(
    #     query_highest_skill, {"user_id": userid, "class_id": classid}
    # ).fetchone()

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

    # Choose the proper prompt template based on question type
    client = openai.OpenAI()

    if order_number is not None:
        fetch_next_order_number(
            db.session, userid, classid, testid, order_number, num_of_items
        )

    # Build prompt for generating all items at once
    prompt_template = (
        config["prompts"]["prompt_mcq_similar"]
        if question_type.lower() == "mc"
        else config["prompts"]["prompt_frq_similar"]
    )

    # Enhance the prompt to request multiple items
    enhanced_description = f"{description}\n\nGenerate EXACTLY {num_of_items} similar question(s). Each question should be unique and meaningfully different from the others."
    
    prompt = prompt_template.format(
        class_name=classid,
        existing_questions=[],
        description=enhanced_description,
        current_item=current_item,
    )

    # Make a single API call to generate all items
    try:
        response = client.responses.parse(
            model=config["gpt_model"]["engine"],
            input=prompt,
            text_format=ExtractedQuestion,
            reasoning={"effort": config["gpt_model"]["reasoning"]},
            text={"verbosity": config["gpt_model"]["verbosity"]},
        )

        result = response.output[1].content[0].parsed
        
        if not hasattr(result, 'questions') or not result.questions:
            return jsonify({"error": "No questions generated"}), 500
        
        # Assign unique IDs to all generated questions
        generated_items = []
        for item in result.questions[:num_of_items]:  # Limit to requested number
            item.item_id = f"{testid}_{str(uuid.uuid4())[:12]}"
            generated_items.append(item)
            
    except Exception as e:
        return jsonify({"error": f"Failed to generate questions: {str(e)}"}), 500

    items = []

    # Process all generated items
    for i, item_response in enumerate(generated_items):
        try:
            # Validate expected fields in the GPT response
            if not hasattr(item_response, "question_part"):
                raise Exception("GPT response missing 'question_part'")
            question = item_response.question_part
            difficulty = item_response.difficulty
            wrong_answer_explanation = getattr(
                item_response, "wrong_answer_explanation", ""
            )
            topics = item_response.relatedtopics
            skills = item_response.relatedskills

            item_id = item_response.item_id
            question_format = item_response.format

            if question_format == "MC":
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

            # Perform the database insertions and commit explicitly.
            # IMPORTANT: Insert into item_current first to satisfy the foreign key in item_history.
            try:
                # Insert into item_current
                insert_item_current(db.session, userid, classid, item_id, 0)
                # db.session.execute(
                #     text(
                #         """
                #         INSERT INTO item_current (user_id, class_id, item_id, version)
                #         VALUES (:user_id, :class_id, :item_id, 0)
                #     """
                #     ),
                #     {"user_id": userid, "class_id": classid, "item_id": item_id},
                # )

                # Ensure the user_class exists
                select_unique_class(db.session, userid, classid)
                # existing_class = db.session.execute(
                #     text(
                #         "SELECT 1 FROM user_classes WHERE user_id = :user_id AND class_id = :class_id"
                #     ),
                #     {"user_id": userid, "class_id": classid},
                # ).fetchone()
                # if not existing_class:
                #     db.session.execute(
                #         text(
                #             "INSERT INTO user_classes (user_id, class_id) VALUES (:user_id, :class_id)"
                #         ),
                #         {"user_id": userid, "class_id": classid},
                #     )

                # Insert into item_history
                insert_item_history(
                    db.session,
                    userid,
                    classid,
                    item_id,
                    0,
                    question,
                    answer_part,
                    question_format,
                    difficulty,
                    wrong_answer_explanation,
                )
                # db.session.execute(
                #     text(
                #         """
                #         INSERT INTO item_history 
                #         (user_id, class_id, item_id, version, question_part, answer_part, format, difficulty, wrong_answer_explanation)
                #         VALUES 
                #         (:user_id, :class_id, :item_id, 0, :question_part, :answer_part, :format, :difficulty, :wrong_answer_explanation)
                #     """
                #     ),
                #     {
                #         "user_id": userid,
                #         "class_id": classid,
                #         "item_id": item_id,
                #         "question_part": question,
                #         "answer_part": answer_part,
                #         "format": question_format,
                #         "difficulty": difficulty,
                #         "wrong_answer_explanation": wrong_answer_explanation,
                #     },
                # )

                # Get the appropriate order number
                if i == 0 and order_number is not None:
                    current_order = order_number
                elif order_number is not None:
                    current_order = order_number + i
                else:
                    current_order = fetch_next_order_number(
                        db.session, userid, classid, testid
                    )

                # Insert into tests
                insert_tests(db.session, userid, classid, testid, item_id, current_order)
                # db.session.execute(
                #     text(
                #         """
                #         INSERT INTO tests 
                #         (user_id, class_id, test_id, item_id, order_number)
                #         VALUES 
                #         (:user_id, :class_id, :testid, :item_id, :order_number)
                #     """
                #     ),
                #     {
                #         "user_id": userid,
                #         "class_id": classid,
                #         "testid": testid,
                #         "item_id": item_id,
                #         "order_number": current_order,
                #     },
                # )

                # Insert into item_topics
                for topic in topics:
                    current_topic_id = get_next_id(current_topic_id, "topic")
                    insert_item_topics(db.session, userid, classid, item_id, 0, current_topic_id, topic)
                    # db.session.execute(
                    #     text(
                    #         """
                    #         INSERT INTO item_topics 
                    #         (user_id, class_id, item_id, version, topic_id, topic_name)
                    #         VALUES 
                    #         (:user_id, :class_id, :item_id, 0, :topic_id, :topic_name)
                    #     """
                    #     ),
                    #     {
                    #         "user_id": userid,
                    #         "class_id": classid,
                    #         "item_id": item_id,
                    #         "topic_id": current_topic_id,
                    #         "topic_name": topic,
                    #     },
                    # )

                # Insert into item_skills
                for skill in skills:
                    current_skill_id = get_next_id(current_skill_id, "skill")
                    insert_item_skills(db.session, userid, classid, item_id, 0, current_skill_id, skill)
                    # db.session.execute(
                    #     text(
                    #         """
                    #         INSERT INTO item_skills 
                    #         (user_id, class_id, item_id, version, skill_id, skill_name)
                    #         VALUES 
                    #         (:user_id, :class_id, :item_id, 0, :skill_id, :skill_name)
                    #     """
                    #     ),
                    #     {
                    #         "user_id": userid,
                    #         "class_id": classid,
                    #         "item_id": item_id,
                    #         "skill_id": current_skill_id,
                    #         "skill_name": skill,
                    #     },
                    # )

                db.session.commit()
            except Exception as db_e:
                db.session.rollback()
                raise db_e

            item = {
                "item_id": item_id,
                "question": question,
                "answer_part": answer_part,
                "difficulty": difficulty,
                "format": question_format,
                "wrong_answer_explanation": wrong_answer_explanation,
                "order_number": current_order,
            }
            items.append(item)
        except Exception as e:
            db.session.rollback()
            return jsonify({"message": "Error generating item", "error": str(e)}), 500

    return (
        jsonify(
            {
                "message": "Item generated successfully",
                "items": items,
            }
        ),
        200,
    )