"""
Filename: modification_routes.py
Description: Routes for modifying existing items.
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
from models import MultipleChoiceItem, FreeResponseItem, EditedItemComponent
from ...utils.class_info import get_class_info
from ...utils.db_operations import (
    fetch_item_latest_version,
    fetch_item_data,
    add_requirement_to_database,
    fetch_item_latest_version
)
from ...utils.compare_reqs import compare_reqs

# Load config.yaml
config_path = os.path.join(os.path.dirname(__file__), "../../utils/config.yaml")
with open(config_path, "r", encoding="utf-8") as f:
    config = yaml.safe_load(f)


@gpt_bp.route("/modify-item", methods=["POST", "OPTIONS"])
def modify_item():
    """
    Generates a modified item using the GPT API.

    Args (from post request):
        userid (str): ID of user
        classid (str): ID for class that item belongs to
        itemid (str): ID of item to regenerate
        version (int): current version number of item
        modification List(str): tuple consisting of [user modification, developer content]

    Returns:
        None, adds new item to database
    """
    # Handle the OPTIONS request explicitly here (CORS headers)
    if request.method == "OPTIONS":
        response = make_response("", 200)
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        return response

    data = request.get_json()
    if not data:
        return jsonify({"message": "No input data provided"}), 400

    print("Modifying item...")

    userid = data.get("userid")
    classid = data.get("classid")
    testid = data.get("testid")
    itemid = data.get("itemid")
    version = fetch_item_latest_version(userid, classid, itemid)
    modification = data.get("modification")
    format = data.get("format")

    info = get_class_info(userid, classid)
    classname = info["class_id"]
    classdesc = info["class_description"]

    user_modification = modification[0]  # Extract user part of modification
    modification = "".join(modification)

    # Adds the user requirement to the database
    req_id = (
        f"{(userid+classid+testid+itemid).replace(' ', '_')}_{str(uuid.uuid4())[:12]}"
    )

    contentType = {
        "question": True,
        "answer": True,
        "wrongAnswerExplanation": True,
        "topics": True,
        "skills": True,
    }

    comparison = compare_reqs(db, userid, modification)
    if comparison == '{"requirementCheck":"False"}':
        if modification:
            add_requirement_to_database(
                userid,
                classid,
                testid,
                itemid,
                req_id,
                0,
                user_modification,
                1,
                1,
                contentType,
            )

    client = openai.OpenAI()

    try:
        # Find item in item_history
        item = fetch_item_data(db.session, userid, classid, itemid, version)
        # query = text(
        #     """
        #     SELECT question_part, answer_part, format, difficulty, wrong_answer_explanation
        #     FROM item_history
        #     WHERE user_id = :user_id AND class_id = :class_id AND item_id = :item_id AND version = :version
        #     """
        # )
        # query_result = db.session.execute(
        #     query,
        #     {
        #         "user_id": userid,
        #         "class_id": classid,
        #         "item_id": itemid,
        #         "version": version,
        #     },
        # ).fetchall()

        # if not query_result:
        #     return jsonify({"message": "Item not found in item_history table"}), 404

        col_names = [
            "question_part",
            "answer_part",
            "format",
            "difficulty",
            "wrong_answer_explanation",
        ]
        generated_item = {key: item[key] for key in col_names}

        if format == "MC":
            print("MC modification")
            user_content = config["prompts"]["modification_MCQ"].format(
                class_name=classname,
                class_description=classdesc,
                generated_item=generated_item,
                modification=modification,
            )

            response = client.responses.parse(
                model=config["gpt_model"]["engine"],
                input=user_content,
                text_format=MultipleChoiceItem,
                reasoning={"effort": config["gpt_model"]["reasoning"]},
                text={"verbosity": config["gpt_model"]["verbosity"]},
            )

            # Extract the parsed response from GPT's output.
            item_response = response.output[1].content[0].parsed

            # Extract attributes from the `item_response` object
            answer_A = item_response.answer_A
            answer_B = item_response.answer_B
            answer_C = item_response.answer_C
            answer_D = item_response.answer_D
            correct_answer = item_response.correct_answer
            wrong_answer_explanation = item_response.wrong_answer_explanation

            # answer_part is concatenation

            answer_part = {}
            answer_part["A"] = answer_A
            answer_part["B"] = answer_B
            answer_part["C"] = answer_C
            answer_part["D"] = answer_D
            answer_part["Correct"] = correct_answer
            answer_part = json.dumps(answer_part)
        else:
            user_content = config["prompts"]["modification_FRQ"].format(
                class_name=classname,
                class_description=classdesc,
                generated_item=generated_item,
                modification=modification,
            )

            response = client.responses.parse(
                model=config["gpt_model"]["engine"],
                input=user_content,
                text_format=FreeResponseItem,
                reasoning={"effort": config["gpt_model"]["reasoning"]},
                text={"verbosity": config["gpt_model"]["verbosity"]},
            )

            # Extract the parsed response from GPT's output.
            item_response = response.output[1].content[0].parsed

            # Extract attributes from the `item_response` object
            wrong_answer_explanation = ""
            # Extract suggested rubric from the `item_response` object
            wrong_answer_explanation = item_response.wrong_answer_explanation

            # answer_part is concatenation
            answer_part = item_response.answer_part

        question = item_response.question_part
        difficulty = item_response.difficulty
        relatedtopics = item_response.relatedtopics
        relatedskills = item_response.relatedskills

        # Set the next version to be the highest version existing + 1
        # query = text(
        #     """
        #     SELECT MAX(version) AS highest_version
        #     FROM item_history
        #     WHERE item_id = :item_id
        # """
        # )
        # result = db.session.execute(query, {"item_id": itemid}).fetchone()
        result = fetch_item_latest_version(userid, classid, itemid)
        highest_version = result + 1

        modify_item = {
            "version": highest_version,
            "question": question,
            "answer": answer_part,
            "format": format,
            "difficulty": difficulty,
            "topics": relatedtopics,
            "skills": relatedskills,
            "wrongAnswerExplanation": wrong_answer_explanation,
        }

        response_data = {
            "item_info": modify_item,
            "message": "Item generated successfully",
        }

        return jsonify(response_data), 200

    except Exception as e:
        return f"Connection failed: {str(e)}", 500


@gpt_bp.route("/edit-item-component", methods=["POST", "OPTIONS"])
def edit_item_component():
    """
    Edits a specific component of an item (question, answer, etc.) using GPT API.

    Args:
        userid (str): User ID
        classid (str): Class ID
        itemid (str): Item ID
        contentType (str): Type of content to edit (question, answer, etc.)
        fullContent (str): Full content of item
        selectedText (str): Text to be edited
        prompt (str): User prompt for editing
        optionKey (str): To identify specific options in MC items
        format (str): Format of the item (MC or FR)

    Returns:
        JSON response with the edited item details.
    """

    # Handle CORS OPTIONS request
    if request.method == "OPTIONS":
        response = make_response("", 200)
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        return response

    # Parse request data
    data = request.get_json()
    if not data:
        return (
            jsonify({"message": "No input data to edit item component provided"}),
            400,
        )

    print("Editing item component...")

    userId = data.get("userid")
    classId = data.get("classid")
    testId = data.get("testid")
    itemId = data.get("itemid")
    contentType = data.get("contentType")
    fullContent = data.get("fullContent")
    selectedText = data.get("selectedText")
    userPrompt = data.get("prompt")
    optionKey = data.get("optionKey")
    itemFormat = data.get("format")

    # Construct GPT prompt
    prompt_template = config["prompts"]["edit_item_component"]
    prompt = prompt_template.format(
        contentType=contentType,
        fullContent=fullContent,
        selectedText=selectedText,
        userPrompt=userPrompt,
        itemFormat=itemFormat,
        optionKey=optionKey,
    )

    # Make API call
    client = openai.OpenAI()
    try:
        response = client.responses.parse(
            model=config["gpt_model"]["engine"],
            input=prompt,
            text_format=EditedItemComponent,
            reasoning={"effort": config["gpt_model"]["reasoning"]},
            text={"verbosity": config["gpt_model"]["verbosity"]},
        )

        # Extract the parsed response from GPT's output.
        editedComponent_response = response.output[1].content[0].parsed
        editedComponent = editedComponent_response.editedComponent

        # Get current item data from DB
        current_version = fetch_item_latest_version(userId, classId, itemId)

        # Add user prompt as a new requirement
        requirement_id = f"{userId.replace(' ', '')}_{classId.replace(' ', '')}_{testId.replace(' ', '')}_{itemId.replace(' ', '')}_{str(uuid.uuid4())[:12]}"
        req_version = 0

        contentType = {
            "question": True if contentType == "question" else False,
            "answer": True if contentType == "answer" else False,
            "wrongAnswerExplanation": (
                True if contentType == "wrongAnswerExplanation" else False
            ),
            "topics": True if contentType == "topics" else False,
            "skills": True if contentType == "skills" else False,
        }

        comparison = compare_reqs(db, userId, userPrompt)

        if comparison == '{"requirementCheck":"False"}':

            # IF function thinks different do:
            add_requirement_to_database(
                user_id=userId,
                class_id=classId,
                test_id=testId,
                item_id=requirement_id,
                req_id=requirement_id,
                version=req_version,
                content=userPrompt,
                usage_count=1,
                application_count=1,
                contentType=contentType,
            )

            # Return changed component
            return (
                jsonify(
                    {
                        "message": "Item component edited successfully (new req added)",
                        "editedComponent": editedComponent,
                    }
                ),
                200,
            )
        else:
            return (
                jsonify(
                    {
                        "message": "Item component edited successfully (No req added)",
                        "editedComponent": editedComponent,
                    }
                ),
                200,
            )

    except Exception as e:
        print("Error during GPT API call:", str(e))
        return jsonify({"message": "Error during GPT API call", "error": str(e)}), 500