# Filename: item_routes.py
# Description: Defines routes for item (question) management.

from flask import request, jsonify
from sqlalchemy import select, func
from app import db
import uuid
from flask import make_response
from .db_blueprint import db_bp
from app.utils.db_operations import add_to_database, fetch_item_data, fetch_item_latest_version
from .table_models import (
    Tests,
    ItemCurrent,
    ItemHistory,
    ItemTopics,
    ItemSkills,
)

################
# Fetch Methods
################

@db_bp.route(
    "/fetch-by-test-id/<string:userid>/<string:classid>/<string:testid>",
    methods=["GET"],
)
def fetch_by_test_id(userid, classid, testid):
    """Fetch items and all related data by test ID."""
    
    try:
        # Step 1: Fetch the item_id and order_number from the tests table
        test_results = select(Tests.item_id, Tests.order_number).filter(
            Tests.user_id == userid,
            Tests.class_id == classid,
            Tests.test_id == testid
        ).order_by(Tests.order_number.asc())

        test_exists = db.session.execute(test_results).all()
        if not test_exists:
            return jsonify({"message": "No items in this test"}), 200
        
        # Store both item_id and order_number in a dictionary for quick lookup
        item_order_map = {item[0]: item[1] for item in test_exists}
        item_id_list = list(item_order_map.keys())

        # Step 2: Fetch the version from the item_current table
        current_version_stmt = select(ItemCurrent.item_id, ItemCurrent.version).filter(
            ItemCurrent.user_id == userid,
            ItemCurrent.class_id == classid,
            ItemCurrent.item_id.in_(item_id_list)
        )
        version_results = db.session.execute(current_version_stmt).all()
        version_map = {item_id: version for item_id, version in version_results}
        if not version_results:
            return jsonify({"message": "Item not found in item_current table"}), 404

        # Step 3: Fetch item data from the item_history table using version
        all_items = []
        for item_id in item_id_list: 
            version = version_map.get(item_id)
            
            item_data = fetch_item_data(userid, classid, item_id, version)
            item_data['test_id'] = testid
            item_data['order_number'] = item_order_map.get(item_id)
            item_data['topics'] = item_data.pop('relatedtopics')
            item_data['skills'] = item_data.pop('relatedskills')
            all_items.append(item_data)

        if not all_items:
            return jsonify({"message": "No item history found for the specified items"}), 404

        # Return the collected data sorted by order_number
        all_items.sort(key=lambda x: x['order_number'])
        return {
            "message": "Data fetched successfully",
            "items": all_items,
        }, 200

    except Exception as e:
        return f"Connection failed: {str(e)}", 500
    
    
@db_bp.route(
    "/fetch-by-user-id/<string:userid>",
    methods=["GET"],
)
def fetch_by_user_id(userid):
    """Fetch items and all related data by test ID."""
    
    try:
        # Step 1: Fetch the item_id and order_number from for all user's tests
        test_results = select(Tests.item_id, Tests.order_number, Tests.test_id, Tests.class_id).filter(
            Tests.user_id == userid,
        ).order_by(Tests.order_number.asc())

        test_exists = db.session.execute(test_results).all()
        if not test_exists:
            return jsonify({"message": "No items in this test"}), 200
        
        # Store both item_id and order_number in a dictionary for quick lookup
        item_details = {
            item_id: {'order_number': order_num, 'test_id': test_id, 'class_id': class_id}
            for item_id, order_num, test_id, class_id in test_exists
        }
        item_id_list = list(item_details.keys())

        # Step 2: Fetch the version from the item_current table
        current_version_stmt = select(ItemCurrent.item_id, ItemCurrent.version).filter(
            ItemCurrent.user_id == userid,
            ItemCurrent.item_id.in_(item_id_list)
        )
        version_results = db.session.execute(current_version_stmt).all()
        version_map = {item_id: version for item_id, version in version_results}
        if not version_results:
            return jsonify({"message": "Item not found in item_current table"}), 404

        # Step 3: Fetch item data for each item's current version
        all_items = []
        for item_id in item_id_list: 
            version = version_map.get(item_id)
            details = item_details.get(item_id)
            classid = details['class_id']
            
            item_data = fetch_item_data(userid, classid, item_id, version)
            item_data["class_id"] = classid
            item_data["item_id"] = item_id
            item_data['test_id'] = details['test_id']
            item_data['order_number'] = details['order_number']
            item_data['topics'] = item_data.pop('relatedtopics')
            item_data['skills'] = item_data.pop('relatedskills')
            all_items.append(item_data)

        if not all_items:
            return jsonify({"message": "No item history found for the specified items"}), 404

        # Return the collected data sorted by order_number
        all_items.sort(key=lambda x: x['order_number'])
        return {
            "message": "Data fetched successfully",
            "items": all_items,
        }, 200

    except Exception as e:
        return f"Connection failed: {str(e)}", 500


@db_bp.route("/fetch-last-version-of-item", methods=["POST"])
def fetch_last_version_of_item():
    """
    Fetch the previous version of an item (the version before the current one).
    """
    data = request.get_json()
    if not data or not all(k in data for k in ["userid", "classid", "itemid"]):
        return jsonify({"message": "Missing or invalid request body"}), 400

    userid = data["userid"]
    classid = data["classid"]
    itemid = data["itemid"]

    try:
        # Get the max version (current version)
        max_version_stmt = select(func.max(ItemHistory.version)).filter(
            ItemHistory.user_id == userid,
            ItemHistory.class_id == classid,
            ItemHistory.item_id == itemid
        )
        max_version = db.session.execute(max_version_stmt).scalar()
        
        # Calculate the previous version
        previous_version = max_version - 1 if max_version is not None and max_version > 0 else None
        
        if previous_version is None:
            return jsonify({
                "message": "No previous version exists for this item",
                "success": False
            }), 404

        # Fetch all data for the previous version using the helper function
        item_data = fetch_item_data(userid, classid, itemid, previous_version)
        item_data['topics'] = item_data.pop('relatedtopics')
        item_data['skills'] = item_data.pop('relatedskills')
        
        if not item_data:
            return jsonify({
                "message": "Previous version data not found in history",
                "success": False
            }), 404

        return jsonify({
            "message": "Previous version fetched successfully",
            "success": True,
            "item": item_data
        }), 200
    
    except Exception as e:
        db.session.rollback()
        return jsonify({
            "message": f"Failed to fetch previous version of item: {str(e)}",
            "success": False
        }), 500


#################
# Mutator Methods
#################

@db_bp.route("/add-item", methods=["POST"])
def add_item():
    """
    Adds a new item to the database.
    """
    data = request.get_json()
    if not data:
        return jsonify({"message": "No input data provided"}), 400
    
    try:
        user_id = data.get('userId')
        test_id = data.get('testId')
        class_id = data.get('classId')
        u4 = str(uuid.uuid4())
        item_id = f"{user_id}_{class_id}_{u4}"
        question = data.get('question')
        answer = data.get('answer')
        format_type = data.get('format')
        difficulty = data.get('difficulty')
        topics = data.get('topics', [])
        skills = data.get('skills', [])
        current_version = 0 # New item starts at version 0
        wrong_answer_explanation = data.get('wrongAnswerExplanation')
        order_number = data.get('orderNumber')

        if not all([user_id, class_id, test_id, question, answer, format_type, difficulty]):
            return jsonify({"message": "Missing required fields"}), 400

        try: 
            # This logic remains as it calls an external, assumed utility function
            questions = [
                {
                    "topic": "General",
                    "subtopic": "General",
                    "questions": [
                        {
                            "question_part": question,
                            "answer_part": answer,
                            "format": format_type,
                            "difficulty": difficulty,
                            "wrong_answer_explanation": wrong_answer_explanation,
                            "relatedtopics": topics,
                            "relatedskills": skills,
                            "item_id": item_id, # Pass new item_id to utility
                        }
                    ]
                }
            ]
            add_to_database(db.session, user_id, class_id, test_id, questions, order_number)

            return jsonify({
                "message": "Item added successfully",
                "data": {
                    "userId": user_id,
                    "classId": class_id,
                    "testId": test_id,
                    "itemId": item_id, 
                    "version": current_version,
                    "question": question,
                    "answer": answer,
                    "format": format_type,
                    "topics": topics,
                    "skills": skills,
                    "difficulty": difficulty,
                    "wrongAnswerExplanation": wrong_answer_explanation,
                    "orderNumber": order_number
                }
            }), 200

        except Exception as e:
            db.session.rollback()
            return jsonify({"message": f"Database transaction failed: {str(e)}"}), 500

    except Exception as e:
        return jsonify({"message": f"Error adding item: {str(e)}"}), 500


@db_bp.route("/copy-item", methods=["POST"])
def copy_item():
    """
    Copies an item, duplicating all related data and inserts below the target item.
    """
    data = request.get_json()
    if not data:
        return jsonify({"message": "Missing data"}), 400

    user_id = data["userId"]
    class_id = data["classId"]
    test_id = data["testId"]
    old_item_id = data["itemId"]
    old_version = fetch_item_latest_version(user_id, class_id, old_item_id)

    # Generate a new item_id for this copy item
    new_item_id = f"{old_item_id}_{uuid.uuid4().hex[:6]}"

    try:
        # 1. Get current order number
        old_test_entry = db.session.execute(
            select(Tests).filter(
                Tests.user_id == user_id,
                Tests.class_id == class_id,
                Tests.test_id == test_id,
                Tests.item_id == old_item_id
            )
        ).scalar_one_or_none()

        if not old_test_entry:
            return jsonify({"message": "Original item not found in test"}), 400

        old_order = old_test_entry.order_number
        new_order = old_order + 1  # Place the copied item right after the original

        # 2. Update order numbers for items after the insertion point
        db.session.query(Tests).filter(
            Tests.user_id == user_id,
            Tests.class_id == class_id,
            Tests.test_id == test_id,
            Tests.order_number >= new_order
        ).update(
            {Tests.order_number: Tests.order_number + 1},
            synchronize_session=False
        )

        # 3. Insert copied item into item_current: new version = 0
        db.session.add(ItemCurrent(
            user_id=user_id, class_id=class_id, item_id=new_item_id, version=0
        ))

        # 4. Fetch target item's data and insert copied item into item_history
        history_to_copy = db.session.execute(
            select(ItemHistory).filter(
                ItemHistory.user_id == user_id,
                ItemHistory.class_id == class_id,
                ItemHistory.item_id == old_item_id,
                ItemHistory.version == old_version
            )
        ).scalar_one_or_none()

        if not history_to_copy:
             # Rollback and return if the history data doesn't exist
            db.session.rollback()
            return jsonify({"message": "Item history not found for copy operation"}), 404
        
        # Insert into item_history (new version = 0)
        db.session.add(ItemHistory(
            user_id=user_id, class_id=class_id, item_id=new_item_id, version=0,
            question_part=history_to_copy.question_part,
            answer_part=history_to_copy.answer_part,
            format=history_to_copy.format,
            difficulty=history_to_copy.difficulty,
            wrong_answer_explanation=history_to_copy.wrong_answer_explanation
        ))

        # 5. Copy and insert into item_topics and item_skills
        topics_to_copy = db.session.execute(
            select(ItemTopics).filter(
                ItemTopics.user_id == user_id,
                ItemTopics.class_id == class_id,
                ItemTopics.item_id == old_item_id,
                ItemTopics.version == old_version
            )
        ).scalars().all()
        for topic in topics_to_copy:
            db.session.add(ItemTopics(
                user_id=user_id, class_id=class_id, item_id=new_item_id, version=0,
                topic_id=topic.topic_id, topic_name=topic.topic_name
            ))

        # Copy item_skills
        skills_to_copy = db.session.execute(
            select(ItemSkills).filter(
                ItemSkills.user_id == user_id,
                ItemSkills.class_id == class_id,
                ItemSkills.item_id == old_item_id,
                ItemSkills.version == old_version
            )
        ).scalars().all()
        for skill in skills_to_copy:
            db.session.add(ItemSkills(
                user_id=user_id, class_id=class_id, item_id=new_item_id, version=0,
                skill_id=skill.skill_id, skill_name=skill.skill_name
            ))

        # 5. Insert into tests
        db.session.add(Tests(
            user_id=user_id, class_id=class_id, test_id=test_id, item_id=new_item_id, order_number=new_order
        ))

        db.session.commit()
        return jsonify({
            "message": "Item duplicated successfully",
            "newItemId": new_item_id
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({"message": f"Failed to copy item: {str(e)}"}), 500


@db_bp.route("/update-item", methods=["PUT"])
def update_item():
    """
    Updates an existing item with new data and increments its version.
    """
    data = request.get_json()
    if not data:
        return jsonify({"message": "No input data provided"}), 400

    try:
        # Extract fields from request
        user_id = data.get('userId')
        class_id = data.get('classId')
        item_id = data.get('itemId')
        question = data.get('question')
        answer = data.get('answer')
        format_type = data.get('format')
        difficulty = data.get('difficulty')
        topics = data.get('topics', [])
        skills = data.get('skills', [])
        wrong_answer_explanation = data.get('wrongAnswerExplanation')
        
        # Validate required fields
        if not all([user_id, class_id, item_id, question, answer, format_type, difficulty]):
            return jsonify({"message": "Missing required fields"}), 400

        try:
            # Get current version and calculate new version
            result = fetch_item_latest_version(user_id, class_id, item_id)
            new_version = result + 1

            # Find latest topic_id
            latest_topic_id = db.session.execute(
                select(ItemTopics.topic_id).filter_by(
                    user_id=user_id, class_id=class_id
                ).order_by(ItemTopics.topic_id.desc()).limit(1)
            ).scalar_one_or_none()

            # Find latest skill_id
            latest_skill_id = db.session.execute(
                select(ItemSkills.skill_id).filter_by(
                    user_id=user_id, class_id=class_id
                ).order_by(ItemSkills.skill_id.desc()).limit(1)
            ).scalar_one_or_none()

            # Get next IDs
            def get_next_id(current_id, prefix):
                if not current_id:
                    return f"{prefix}_0"
                try:
                    num = int(current_id.split('_')[1])
                    return f"{prefix}_{num + 1}"
                except (IndexError, ValueError):
                    return f"{prefix}_0"

            # Update item_current
            db.session.query(ItemCurrent).filter_by(
                user_id=user_id, class_id=class_id, item_id=item_id
            ).update({ItemCurrent.version: new_version}, synchronize_session=False)

            # Insert into item_history
            db.session.add(ItemHistory(
                user_id=user_id, class_id=class_id, item_id=item_id, version=new_version,
                question_part=question, answer_part=answer, format=format_type, 
                difficulty=difficulty, wrong_answer_explanation=wrong_answer_explanation
            ))

            # Insert topics
            current_topic_id = latest_topic_id
            for topic in topics:
                next_topic_id = get_next_id(current_topic_id, "topic") 
                db.session.add(ItemTopics(
                    user_id=user_id, class_id=class_id, item_id=item_id, version=new_version,
                    topic_id=next_topic_id, topic_name=topic
                ))
                current_topic_id = next_topic_id # Update for next iteration

            # Insert skills
            current_skill_id = latest_skill_id
            for skill in skills:
                next_skill_id = get_next_id(current_skill_id, "skill")
                db.session.add(ItemSkills(
                    user_id=user_id, class_id=class_id, item_id=item_id, version=new_version,
                    skill_id=next_skill_id, skill_name=skill
                ))
                current_skill_id = next_skill_id

            db.session.commit()

            return jsonify({
                "message": "Item updated successfully",
                "data": {
                    "userId": user_id,
                    "classId": class_id,
                    "itemId": item_id,
                    "version": new_version,
                    "question": question,
                    "answer": answer,
                    "format": format_type,
                    "topics": topics,
                    "skills": skills,
                    "difficulty": difficulty,
                    "wrongAnswerExplanation": wrong_answer_explanation
                }
            }), 200

        except Exception as e:
            db.session.rollback()
            return jsonify({"message": f"Database transaction failed: {str(e)}"}), 500

    except Exception as e:
        return jsonify({"message": f"Error updating item: {str(e)}"}), 500


@db_bp.route("/update_item_order", methods=["POST"])
def update_item_order():
    """
    Update the order of an item within a test.
    """
    
    data = request.get_json()
    if not data:
        return jsonify({"message": "No input data provided"}), 400

    user_id = data.get('userId')
    class_id = data.get('classId')
    test_id = data.get('testId')
    item_id = data.get('itemId')
    old_order_number = data.get("oldOrderNumber")
    new_order_number = data.get('newOrderNumber')

    if not all([user_id, class_id, test_id, item_id, old_order_number, new_order_number]):
        return jsonify({"message": "Missing required fields"}), 400
    
    try:
        # 1. Update the moved item's order number
        db.session.query(Tests).filter_by(
            user_id=user_id, class_id=class_id, test_id=test_id, item_id=item_id
        ).update(
            {Tests.order_number: new_order_number}, 
            synchronize_session=False
        )
        
        # 2. Shift the order numbers of other items
        filter_args = [
            Tests.user_id == user_id,
            Tests.class_id == class_id,
            Tests.test_id == test_id,
            Tests.item_id != item_id
        ]

        if new_order_number > old_order_number:
            # Item moved down: shift all in between up (decrement order_number)
            db.session.query(Tests).filter(
                *filter_args,
                Tests.order_number.between(old_order_number + 1, new_order_number)
            ).update(
                {Tests.order_number: Tests.order_number - 1}, 
                synchronize_session=False
            )
        elif new_order_number < old_order_number:
            # Item moved up: shift all in between down (increment order_number)
            db.session.query(Tests).filter(
                *filter_args,
                Tests.order_number.between(new_order_number, old_order_number - 1)
            ).update(
                {Tests.order_number: Tests.order_number + 1}, 
                synchronize_session=False
            )
        
        db.session.commit()
        return jsonify({"message": "Item order updated successfully"}), 200
    
    except Exception as e:
        db.session.rollback()
        return jsonify({"message": f"Error updating item order: {str(e)}"}), 500


@db_bp.route("/undo-item", methods=["POST", "OPTIONS"])
def undo_item():
    """
    Undo the latest change made to a specific item.
    """
    # OPTIONS request handling for CORS
    if request.method == 'OPTIONS':
        response = make_response('', 200)
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Methods'] = 'POST, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
        return response
    
    data = request.get_json()
    if not data or "userid" not in data or "classid" not in data or "itemid" not in data:
        return jsonify({"message": "Missing or invalid request body"}), 400
    
    userid = data["userid"]
    classid = data["classid"]
    itemid = data["itemid"]
    
    try:
        # 1. Find the current version of the item
        current_item = db.session.execute(
            select(ItemCurrent).filter_by(
                user_id=userid, class_id=classid, item_id=itemid
            )
        ).scalar_one_or_none()

        if not current_item:
            return jsonify({"message": "Item not found in current table"}), 404
            
        old_version = current_item.version
        
        # Check if there is a version to undo to (version 0 is the base)
        if old_version <= 0:
            return jsonify({"message": "Cannot undo the base version (version 0)"}), 400
            
        new_version = old_version - 1
        
        # 2. Delete obsolete version entries from History, Topics, Skills
        filter_args = {
            "user_id": userid, "class_id": classid, "item_id": itemid, "version": old_version
        }
        
        db.session.query(ItemTopics).filter_by(**filter_args).delete(synchronize_session=False)
        db.session.query(ItemSkills).filter_by(**filter_args).delete(synchronize_session=False)
        db.session.query(ItemHistory).filter_by(**filter_args).delete(synchronize_session=False)
        
        # 3. Update the item version in item_current table
        current_item.version = new_version

        # Note: No need to update item_topics and item_skills table as they are related to item_current via ON_UPDATE_CASCADE

        # 4. Fetch the details of the current version
        item = fetch_item_data(userid, classid, itemid, new_version)
    
        db.session.commit()
    
        return jsonify({"message": "Item undone successfully", "item": item}), 200
    
    except Exception as e:
        print("failed")
        return jsonify({"message": f"Connection failed: {str(e)}"}), 500


@db_bp.route("/delete-item/", methods=["POST"])
def delete_item():
    """
    Deletes an item and its associated data from all related tables.
    """

    data = request.get_json()
    if not data:
        return jsonify({"message": "No input data provided"}), 400

    userid = data.get('userId')
    classid = data.get('classId')
    itemid = data.get('itemId')

    try:
        # 1. Get the order number from the Tests table before deletion
        tests_entry = db.session.execute(
            select(Tests).filter_by(
                user_id=userid, class_id=classid, item_id=itemid
            )
        ).scalar_one_or_none()
        deleted_order_number = tests_entry.order_number if tests_entry else None

        # 2. Delete from item tables by item_id
        filter_args = {
            "user_id": userid, 
            "class_id": classid, 
            "item_id": itemid
        }
        
        tables_to_delete = [ItemSkills, ItemTopics, ItemHistory, Tests, ItemCurrent]
        for Model in tables_to_delete:
            db.session.query(Model).filter_by(**filter_args).delete(synchronize_session=False)
        
        # 3. Adjust order numbers of remaining items in the test
        if deleted_order_number is not None:
            # Decrement order_number for all subsequent items in the test
            db.session.query(Tests).filter(
                Tests.user_id == userid, 
                Tests.class_id == classid,
                Tests.order_number > deleted_order_number
            ).update(
                {Tests.order_number: Tests.order_number - 1}, 
                synchronize_session=False
            )

        db.session.commit()

        return jsonify({"message": "Item successfully deleted"}), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({"message": f"Failed to delete item: {str(e)}"}), 500
