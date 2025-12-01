"""
Filename: requirement_routes.py
Description: Routes for applying and generating requirements.
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
from models import MultipleChoiceItem, FreeResponseItem, RequirementItem
from ...utils.db_operations import (
    fetch_item_latest_version,
    fetch_item_data,
    add_requirement_to_database,
    select_requirements
)
from ...utils.compare_reqs import compare_reqs

# Load config.yaml
config_path = os.path.join(os.path.dirname(__file__), "../../utils/config.yaml")
with open(config_path, "r", encoding="utf-8") as f:
    config = yaml.safe_load(f)



@gpt_bp.route("/apply-requirements", methods=["POST", "OPTIONS"])
def apply_requirements():
    """
    Processes a list of item IDs and requirement content, returns edited items

    Args:
        user id (str)
        class id (str)
        test id (str)
        requirements id(s) (List[str])
        item id(s) (List[str])
    """
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

    print("Applying requirements to items...")

    user_id = data.get("user_id")
    class_id = data.get("class_id")
    req_ids = data.get("req_ids")
    item_ids = data.get("item_ids")

    # Step 1: Fetch requirements and corresponding tags from database
    requirements_dict = {}

    for req_id in req_ids:
        # Find requrirement in database
        result = select_requirements(db.session, user_id, req_id)

        if not result:
            return jsonify({"message": f"Requirement {req_id} not found"}), 404

        content, question, answer, wrong_answer_explanation, topics, skills = result

        requirements_dict[req_id] = {
            "content": content,
            "question": question,
            "answer": answer,
            "wrong_answer_explanation": wrong_answer_explanation,
            "topics": topics,
            "skills": skills,
        }

    # Extract the requirements to be applied
    apply_reqs = [r["content"] for r in requirements_dict.values()]

    # Extract tags indicated for modification (using a Set to avoid duplicates)
    tags = {
        tag
        for r in requirements_dict.values()
        for tag, value in r.items()
        if tag != "content" and value is True
    }

    # Step 2: Initialize prompts and prepare for API call
    req_config = os.path.join(
        os.path.dirname(__file__), "../../utils/requirements_prompt.yaml"
    )
    with open(req_config, "r", encoding="utf-8") as f:
        req_config = yaml.safe_load(f)

    # Organize API call
    client = openai.OpenAI()

    new_items = []

    # Step 3: Iterate through each item and apply requirements to their corresponding tags
    for item_id in item_ids:
        # Get latest verison of item
        latest_ver = fetch_item_latest_version(db.session, user_id, class_id, item_id)

        # Get item data
        item_data = fetch_item_data(db.session, user_id, class_id, item_id, latest_ver)
        item_format = item_data["format"]

        try:
            # All/no tags selected -> (true) edit entire item
            # <5 tags selected -> (false) edit only those tags
            is_full_edit = len(tags) == 5 or len(tags) == 0

            # Multiple Choice Item
            if item_format == "MC":
                if is_full_edit:
                    user_content = req_config["Entire_MCQ_prompt"].format(
                        item_data=str(item_data), requirements=str(apply_reqs)
                    )

                    response = client.responses.parse(
                        model=config["gpt_model"]["engine"],
                        input=user_content,
                        text_format=MultipleChoiceItem,
                        reasoning={"effort": config["gpt_model"]["reasoning"]},
                        text={"verbosity": config["gpt_model"]["verbosity"]},
                    )

                else:
                    user_content = req_config["Partial_MCQ_Prompt"].format(
                        item_data=str(item_data),
                        requirements=str(apply_reqs),
                        item_tags=str(tags),
                    )

                    response = client.responses.parse(
                        model=config["gpt_model"]["engine"],
                        input=user_content,
                        text_format=MultipleChoiceItem,
                        reasoning={"effort": config["gpt_model"]["reasoning"]},
                        text={"verbosity": config["gpt_model"]["verbosity"]},
                    )

                # Extract parsed response
                item_response = response.output[1].content[0].parsed

                # Step 4: Extract answers from response
                answer_A = item_response.answer_A
                answer_B = item_response.answer_B
                answer_C = item_response.answer_C
                answer_D = item_response.answer_D
                correct_answer = item_response.correct_answer

                # Formate MC answers
                answer = {}
                answer["A"] = answer_A
                answer["B"] = answer_B
                answer["C"] = answer_C
                answer["D"] = answer_D
                answer["Correct"] = correct_answer
                answer = json.dumps(answer)

            # Free Response Item
            else:
                if is_full_edit:
                    user_content = req_config["Entire_FRQ_prompt"].format(
                        item_data=str(item_data), requirements=str(apply_reqs)
                    )

                    response = client.responses.parse(
                        model=config["gpt_model"]["engine"],
                        input=user_content,
                        text_format=FreeResponseItem,
                        reasoning={"effort": config["gpt_model"]["reasoning"]},
                        text={"verbosity": config["gpt_model"]["verbosity"]},
                    )

                else:
                    user_content = req_config["Partial_FRQ_Prompt"].format(
                        item_data=str(item_data),
                        requirements=str(apply_reqs),
                        item_tags=str(tags),
                    )

                    response = client.responses.parse(
                        model=config["gpt_model"]["engine"],
                        input=user_content,
                        text_format=FreeResponseItem,
                        reasoning={"effort": config["gpt_model"]["reasoning"]},
                        text={"verbosity": config["gpt_model"]["verbosity"]},
                    )

                # Extract parsed response
                item_response = response.output[1].content[0].parsed
                # Step 4: Extract FR answer
                answer = item_response.answer_part

            # Step 5: Extract other attributes
            question = item_response.question_part
            difficulty = item_response.difficulty
            relatedtopics = item_response.relatedtopics
            relatedskills = item_response.relatedskills
            wrong_answer_explanation = item_response.wrong_answer_explanation

            # Step 6: Construct the modified item
            modify_item = {
                "itemid": item_id,
                "version": latest_ver + 1,
                "question": question,
                "answer": answer,
                "format": item_format,
                "difficulty": difficulty,
                "topics": relatedtopics,
                "skills": relatedskills,
                "wrong_answer_explanation": wrong_answer_explanation,
            }

            # Rename keys of item_data (original data of item )to match with modify item
            remap_keys = {
                "question_part": "question",
                "answer_part": "answer",
                "relatedtopics": "topics",
                "relatedskills": "skills",
            }

            for old_key, new_key in remap_keys.items():
                item_data[new_key] = item_data.pop(old_key)

            # If only some tags are selected, make sure they are the only fields with modified content
            # If 0 or 5 tags are selected, all modified content is kept
            if not is_full_edit:
                for key in modify_item.keys():
                    if key not in tags and key != "itemid" and key != "version":
                        modify_item[key] = item_data[key]

            new_items.append(modify_item)

        except Exception as e:
            return jsonify({"message": f"Connection failed: {str(e)}"}), 500

    response_data = {
        "item_info": new_items,
        "message": "Item generated successfully",
    }

    return jsonify(response_data), 200


@gpt_bp.route("/generate-requirement", methods=["POST", "OPTIONS"])
def generate_requirement():
    """
    Generates a requirement for an item modification through manual OR prompt editing.

    Args:
        userid (str): User ID
        classid (str): Class ID
        testid (str): Test ID
        itemid (str): Item ID

    Returns:
        A JSON response with the generated requirement as a string.
    """
    # Handle CORS OPTIONS request
    if request.method == "OPTIONS":
        response = make_response("", 200)
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        return response

    data = request.get_json()
    if not data:
        return jsonify({"message": "No input data provided for requirements"}), 400

    print("Generating requirement for item...")

    user_id = data.get("userid")
    class_id = data.get("classid")
    test_id = data.get("testid")
    item_id = data.get("itemid")
    contentType = data.get("contentType")  # tags

    # Get latest version of item
    latest_ver = fetch_item_latest_version(db.session, user_id, class_id, item_id)

    # Previous version of item
    prev_ver = latest_ver - 1 if latest_ver > 0 else 0

    # Fetch items from DB
    latest_ver_item = fetch_item_data(db.session, user_id, class_id, item_id, latest_ver)
    previous_ver_item = fetch_item_data(db.session, user_id, class_id, item_id, prev_ver)

    # Construct prompt for GPT
    prompt = config["prompts"]["requirement_template"].format(
        item_old=previous_ver_item, item_new=latest_ver_item
    )

    # Make API call
    client = openai.OpenAI()
    try:
        response = client.responses.parse(
            model=config["gpt_model"]["engine"],
            input=prompt,
            text_format=RequirementItem,
            reasoning={"effort": config["gpt_model"]["reasoning"]},
            text={"verbosity": config["gpt_model"]["verbosity"]},
        )

        requirement_response = response.output[1].content[0].parsed

        # Extract the reasoning from the parsed response
        reasoning = requirement_response.reasoning

        comparison = compare_reqs(db, user_id, reasoning)
        if comparison == '{"requirementCheck":"False"}':

            # Add to database
            requirement_id = (
                f"{user_id}_{class_id}_{test_id}_{item_id}_{str(uuid.uuid4())[:12]}"
            )
            req_version = 0

            add_requirement_to_database(
                user_id=user_id,
                class_id=class_id,
                test_id=test_id,
                item_id=requirement_id,
                req_id=requirement_id,
                version=req_version,
                content=reasoning,
                usage_count=1,
                application_count=1,
                contentType=contentType,
            )

            return (
                jsonify(
                    {
                        "message": "Requirement generated successfully",
                        "requirement": reasoning,
                    }
                ),
                200,
            )
        else:
            return (
                jsonify(
                    {
                        "message": "Requirement already exists",
                        "requirement": reasoning,
                    }
                ),
                200,
            )

    except Exception as e:
        print(f"Error generating requirement: {str(e)}")
        return (
            jsonify({"message": "Error generating requirement", "error": str(e)}),
            500,
        )