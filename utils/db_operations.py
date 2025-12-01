import psycopg2
import uuid
from dotenv import load_dotenv
import os
import json

import sqlalchemy
#orm library is sqlalchemy
from sqlalchemy import text
from sqlalchemy.orm import Session, ForeignKey, String, DeclarativeBase, Mapped, mapped_column, relationship, select, desc


from .table_models import (
    Tests,
    ItemCurrent,
    ItemHistory,
    ItemTopics,
    ItemSkills,
    Requirements,
    UserClasses
)


# HELPER FUNCS!

# Load environment variables
load_dotenv()

def get_db_connection():
    """
    Establish a connection to the PostgreSQL database using environment variables.
    """
    return psycopg2.connect(
        host=os.getenv("DB_HOST"),
        database=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        port=os.getenv("DB_PORT")
    )

def fetch_next_order_number(db_session, user_id, class_id, test_id, desired_order=None, num_items=1):
    """
    Get the next order number for a test item, either at a specific position or at the end.    
    Returns:
        int: The next order number to use
    """
    if desired_order is not None:
        if isinstance(db_session, psycopg2.extensions.cursor):
            db_session.execute("""
                UPDATE tests
                SET order_number = order_number + %s
                WHERE user_id = %s AND class_id = %s AND test_id = %s
                AND order_number >= %s
            """, (num_items, user_id, class_id, test_id, desired_order))
            return desired_order
        else:
            db_session.execute(
                text("""
                    UPDATE tests
                    SET order_number = order_number + :num_items
                    WHERE user_id = :user_id AND class_id = :class_id AND test_id = :test_id
                    AND order_number >= :order_number
                """),
                {
                    "user_id": user_id,
                    "class_id": class_id,
                    "test_id": test_id,
                    "order_number": desired_order,
                    "num_items": num_items
                }
            )
            return desired_order
    
    if isinstance(db_session, psycopg2.extensions.cursor):
        db_session.execute("""
            SELECT COALESCE(MAX(order_number), 0) FROM tests
            WHERE user_id = %s AND class_id = %s AND test_id = %s
        """, (user_id, class_id, test_id))
        max_order = db_session.fetchone()[0]
    else:
        result = db_session.execute(
            text("""
                SELECT COALESCE(MAX(order_number), 0) FROM tests
                WHERE user_id = :user_id AND class_id = :class_id AND test_id = :test_id
            """),
            {
                "user_id": user_id,
                "class_id": class_id,
                "test_id": test_id
            }
        ).scalar()
        max_order = result
    
    return max_order + 1

def fetch_highest_topic_id(db_session, user_id, class_id):

    stmt = (
        select(ItemTopics.topic_id)
        .where(
            ItemTopics.user_id == user_id,
            ItemTopics.class_id == class_id,
        )
        .order_by(desc(ItemTopics.topic_id))
        .limit(1)
    )

   #returns the item topic ID if exists, otherwise returns none
    result = db_session.execute(stmt).scalar_one_or_none()
    return result
    
   
def insert_item_current(db_session, user_id, class_id, item_id, version):

    try:
        curr_item = ItemCurrent(
            user_id = user_id,
            class_id = class_id, 
            item_id = item_id, 
            version = version
        )

        db_session.add(curr_item)
        #db_session.commit()
    except Exception as e:
        print(f"Error inserting test: {e}")
        db_session.rollback()
    


def insert_item_history(db_session, user_id, class_id, item_id, version, question, answer_part, question_type, difficulty, wrong_answer_explanation):
    
    try:
        history_item = ItemHistory(
                user_id = user_id,
                class_id = class_id,
                item_id = item_id,
                version = version,
                question_part = question,
                answer_part = answer_part,
                format = question_type,
                difficulty = difficulty,
                wrong_answer_explanation = wrong_answer_explanation

        )
        db_session.add(history_item)
        #db_session.commit()
    except Exception as e:
        print(f"Error inserting test: {e}")
        db_session.rollback()


    # db_session.execute(
    #     text(
    #         """INSERT INTO item_history 
    #         (user_id, class_id, item_id, version, question_part, answer_part, format, difficulty, wrong_answer_explanation)
    #         VALUES (:user_id, :class_id, :item_id, :version, :question_part, :answer_part, :format, :difficulty, :wrong_answer_explanation)"""
    #     ),
    #     {
    #         "user_id": user_id,
    #         "class_id": class_id,
    #         "item_id": item_id,
    #         "version": version,
    #         "question_part": question,
    #         "answer_part": answer_part,
    #         "format": question_type,
    #         "difficulty": difficulty,
    #         "wrong_answer_explanation": wrong_answer_explanation,
    #     },
    # )


def insert_item_topics(db_session, user_id, class_id, item_id, version, topic_id, topic_name):

    try:
        topic_item = ItemTopics(
                user_id = user_id,
                class_id = class_id,
                item_id = item_id,
                version = version,
                topic_id = topic_id, 
                topic_name = topic_name
        )
        
        db_session.add(topic_item)
        #db_session.commit()
    except Exception as e:
        print(f"Error inserting test: {e}")
        db_session.rollback()

def insert_item_skills(db_session, user_id, class_id, item_id, version, skill_id, skill_name):

    try:
        topic_item = ItemTopics(
                user_id = user_id,
                class_id = class_id,
                item_id = item_id,
                version = version,
                skill_id = skill_id, 
                skill_name = skill_name
        )
        
        db_session.add(topic_item)
        #db_session.commit()
    except Exception as e:
        print(f"Error inserting test: {e}")
        db_session.rollback()

    #  db_session.execute(
    #                 text(
    #                     """INSERT INTO item_skills 
    #                     (user_id, class_id, item_id, version, skill_id, skill_name)
    #                     VALUES (:user_id, :class_id, :item_id, :version, :skill_id, :skill_name)"""
    #                 ),
    #                 {
    #                     "user_id": user_id,
    #                     "class_id": class_id,
    #                     "item_id": item_id,
    #                     "version": version,
    #                     "skill_id": skill_id,
    #                     "skill_name": skill_name,
    #                 },
    #             )

def insert_tests(db_session, user_id, class_id, test_id, item_id, order_number):

    try:
        new_test = Tests(
            user_id=user_id,
            class_id=class_id,
            test_id=test_id,
            item_id=item_id,
            order_number=order_number,
        )

        db_session.add(new_test)
        #db_session.commit()
        print("Insert successful!")

        #return new_test  
    except Exception as e:
        print(f"Error inserting test: {e}")
        db_session.rollback()
        #return None

    # db_session.execute(
    #     text(
    #         """
    #         INSERT INTO tests (user_id, class_id, test_id, item_id, order_number)
    #         VALUES (:user_id, :class_id, :testid, :item_id, :order_number)
    #         """
    #     ),
    #     {
    #         "user_id": user_id,
    #         "class_id": class_id,
    #         "testid": test_id,
    #         "item_id": item_id,
    #         "order_number": order_number,
    #     },
    # )

#COME BACK AND FIX THIS!!!
def select_unique_class(db_session, user_id, class_id):

    existing_class = (
        db_session.query(UserClasses)
        .filter_by(user_id=user_id, class_id=class_id)
        .first()
    )

    if existing_class is None:
        new_class = UserClasses(user_id=user_id, class_id=class_id)
        db_session.add(new_class)
        #db_session.commit()
        return new_class
    else:
        
        return existing_class
    

    # existing_class = db_session.execute(
    #     text(
    #         "SELECT 1 FROM user_classes WHERE user_id = :user_id AND class_id = :class_id"
    #     ),
    #     {"user_id": user_id, "class_id": class_id},
    # ).fetchone()


    # if not existing_class:
    #         db_session.execute(
    #             text(
    #             "INSERT INTO user_classes (user_id, class_id) VALUES (:user_id, :class_id)"
    #             ),
    #             {"user_id": user_id, "class_id": class_id},
    #         )

    # else:
    #     return existing_class
    

def fetch_highest_skill_id(db_session, userid, classid):

    stmt = (
        select(ItemSkills.skill_id)
        .where(
            ItemTopics.user_id == userid,
            ItemTopics.class_id == classid,
        )
        .order_by(desc(ItemSkills.skill_id))
        .limit(1)
    )

    return db_session.execute(stmt).scalar_one_or_none()
    
    # db_session.execute(
    #     text(
    #         """
    #         SELECT skill_id FROM item_skills
    #         WHERE user_id = :user_id AND class_id = :class_id
    #         ORDER BY skill_id DESC LIMIT 1
    #     """
    #     ),
    #     {"user_id": userid, "class_id": classid},
    # )

def select_requirements(db_session, user_id, req_id):

    stmt = (
        select(Requirements.skill_id)
        .where(
            Requirements.user_id == user_id,
            Requirements.req_id == req_id,
        )
    )

    return db_session.execute(stmt).scalar_one_or_none()

    # result = db_session.execute(
    #     text(
    #         """
    #         SELECT content, question, answer, wrong_answer_explanation, topics, skills
    #         FROM requirements
    #         WHERE user_id = :user_id
    #             AND req_id = :req_id
    #     """
    #     ),
    #     {"user_id": user_id, "req_id": req_id},
    # )
    # return result 
    


def add_to_database(db_session, user_id, class_id, test_id, questions, order_number=None):

    try:
       
        existing_class = (
            db_session.query(UserClasses)
            .filter_by(user_id=user_id, class_id=class_id)
            .first()
        )

        if not existing_class:
            new_uc = UserClasses(user_id=user_id, class_id=class_id)
            db_session.add(new_uc)

        # Iterate through each topic and subtopic in the list of questions
        for question_set in questions:
            topic = question_set["topic"]
            subtopic = question_set["subtopic"]
            question_list = question_set["questions"]  # Now a list


            for question in question_list:
                item_id = f"{test_id}_{str(uuid.uuid4())[:12]}"   # Unique item ID
                version = 0

                # Extract common fields
                question_part = question["question_part"]
                difficulty = question["difficulty"]
                format_type = question["format"]
                    
                formatted_question_part = question_part  
                answer_part = question["answer_part"] 
                wrong_answer_explanation = question["wrong_answer_explanation"]

                # Insert into item_current
                #replace with

                item_current = ItemCurrent(
                    user_id=user_id,
                    class_id=class_id,
                    item_id=item_id,
                    version=version,
                )
                db_session.add(item_current)


                item_history = ItemHistory(
                    user_id=user_id,
                    class_id=class_id,
                    item_id=item_id,
                    version=version,
                    question_part=formatted_question_part,
                    answer_part=answer_part,
                    format=format_type,
                    difficulty=difficulty,
                    wrong_answer_explanation=(
                        wrong_answer_explanation if wrong_answer_explanation else None
                    ),
                )
                db_session.add(item_history)

                # Insert into item_history
                # cur.execute("""
                #     INSERT INTO item_history (user_id, class_id, item_id, version, question_part, answer_part, format, difficulty, wrong_answer_explanation)
                #     VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                # """, (
                #     user_id, class_id, item_id, version,
                #     formatted_question_part, answer_part,
                #     format_type, difficulty, wrong_answer_explanation if wrong_answer_explanation else None
                # ))

                # Insert into item_topics
                for related_topic in question.get("relatedtopics", []):
                    related_topic_id = f"{related_topic.replace(' ', '_')}_{class_id}"
                    item_topic = ItemTopics(
                        user_id=user_id,
                        class_id=class_id,
                        item_id=item_id,
                        version=version,
                        topic_id=related_topic_id,
                        topic_name=related_topic,
                    )
                    db_session.add(item_topic)
                    # cur.execute("""
                    #     INSERT INTO item_topics (user_id, class_id, item_id, version, topic_id, topic_name)
                    #     VALUES (%s, %s, %s, %s, %s, %s)
                    # """, (user_id, class_id, item_id, version, related_topic_id, related_topic))

                # Insert into item_skills
                for skill_name in question.get("relatedskills", []):
                    skill_id = f"{skill_name.replace(' ', '_')}_{class_id}"
                    item_skill = ItemSkills(
                        user_id=user_id,
                        class_id=class_id,
                        item_id=item_id,
                        version=version,
                        skill_id=skill_id,
                        skill_name=skill_name,
                    )
                    db_session.add(item_skill)
                    # cur.execute("""
                    #     INSERT INTO item_skills (user_id, class_id, item_id, version, skill_id, skill_name)
                    #     VALUES (%s, %s, %s, %s, %s, %s)
                    # """, (user_id, class_id, item_id, version, skill_id, skill_name))

                new_order = fetch_next_order_number(cur, user_id, class_id, test_id, order_number)

                # Link each question to the test in the `tests` table
                test_row = Tests(
                    user_id=user_id,
                    class_id=class_id,
                    test_id=test_id,
                    item_id=item_id,
                    order_number=new_order,
                )
                db_session.add(test_row)

                # cur.execute("""
                #     INSERT INTO tests (user_id, class_id, test_id, item_id, order_number)
                #     VALUES (%s, %s, %s, %s, %s)
                # """, (user_id, class_id, test_id, item_id, new_order))

        # Commit transaction
        db_session.commit()

    except Exception as e:
        db_session.rollback()
        raise Exception(f"Database operation failed: {e}")
    
    # finally:
    #     cur.close()
    #     conn.close()

def fetch_item_latest_version(db_session, user_id, class_id, item_id):
    
    try:
        # Get the latest version of the item
        # cur.execute("""
        #     SELECT version FROM item_current
        #     WHERE user_id = %s AND class_id = %s AND item_id = %s
        # """, (user_id, class_id, item_id))
        # latest_version = cur.fetchone()
        
        latest_version = (
            db_session.query(ItemCurrent.version)
            .filter_by(user_id=user_id, class_id=class_id, item_id=item_id)
            .first()
        )

        if latest_version:
            return latest_version[0]
        else:
            raise Exception("Item not found")
    except Exception as e:
        raise Exception(f"Failed to fetch latest version: {e}")
    
   
def fetch_item_data(db_session, user_id, class_id, item_id, version):
    # conn = get_db_connection()
    # cur = conn.cursor()
    
    try:
        # Get the item details from item_history

        fetch_all_from_item_history = (
        select(ItemHistory.question_part, ItemHistory.answer_part, ItemHistory.format, ItemHistory.difficulty, ItemHistory.wrong_answer_explanation)
        .where(
            ItemHistory.user_id == user_id,
            ItemHistory.class_id == class_id,
            ItemHistory.item_id == item_id, 
            ItemHistory.version == version
        )
        )

        item_data = db_session.execute(fetch_all_from_item_history).scalar_one_or_none()
        
        # cur.execute("""
        #     SELECT question_part, answer_part, format, difficulty, wrong_answer_explanation 
        #     FROM item_history
        #     WHERE user_id = %s AND class_id = %s AND item_id = %s AND version = %s
        # """, (user_id, class_id, item_id, version))
        #item_data = cur.fetchone()
        
        if not item_data: raise Exception("Item not found in history.")
        
        # Get item topics from item_topics
        fetch_topic = (
        select(ItemTopics.topic_name)
        .where(
            ItemTopics.user_id == user_id,
            ItemTopics.class_id == class_id,
            ItemTopics.item_id == item_id, 
            ItemTopics.version == version
        )
        )
        item_topics = db_session.execute(fetch_topic).scalar_one_or_none()

        # cur.execute("""
        #     SELECT topic_name 
        #     FROM item_topics
        #     WHERE user_id = %s AND class_id = %s AND item_id = %s AND version = %s
        # """, (user_id, class_id, item_id, version))
        # item_topics = cur.fetchall()
        
        item_topics = [topic[0] for topic in item_topics]
        
        # Get item skills form item_skills
        stmt = (
        select(ItemSkills.skill_name)
        .where(
            ItemSkills.user_id == user_id,
            ItemSkills.class_id == class_id,
            ItemSkills.version == version
        )
        )

        item_skills = db_session.execute(stmt).scalar_one_or_none()
        item_skills = [skill[0] for skill in item_skills]

         # cur.execute("""
        #     SELECT skill_name
        #     FROM item_skills
        #     WHERE user_id = %s AND class_id = %s  AND item_id = %s AND version = %s
        # """, (user_id, class_id, item_id, version))
        # item_skills = cur.fetchall()
        
        # Populate item for return
        col_names = [
            "question_part",
            "answer_part",
            "format",
            "difficulty",
            "wrong_answer_explanation",
            ]
        item = dict(zip(col_names, item_data))
        item["relatedtopics"] = item_topics
        item["relatedskills"] = item_skills
        item["item_id"] = item_id
        item["class_id"] = class_id
        item["user_id"] = user_id
        
        return item

    except Exception as e:
        raise Exception(f"Failed to fetch item details: {e}")
    
    # finally:
    #     cur.close()
    #     conn.close()

def add_requirement_to_database(db_session, user_id, class_id, test_id, item_id, req_id, version, content, usage_count, application_count, contentType):
    """
    Save requirement into the database.
    
    Args:
        user_id (str): The user's ID.
        class_id (str): The class ID.
        item_id (str): The item ID.
        req_id (str): The requirement ID.
        version (int): The version number.
        content (str): The requirement content.
        usage_count (int): The usage count of the requirement.
        application_count (int): The application count of the requirement.
        contentType (Dict[str, bool]): The tags this requirement is generated for. 
            (e.g. {"question": True, "answer": False, "wrongAnswerAxplanation": False, ...})
        
    Returns:
        None
    """
    required_keys = ["question", "answer", "wrongAnswerExplanation", "topics", "skills"]
    flags = [contentType.get(key, False) for key in required_keys]

    query = """
        INSERT INTO requirements (
            user_id, class_id, test_id, item_id, req_id, version, 
            content, usage_count, application_count, 
            question, answer, wrong_answer_explanation, topics, skills
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """

    values = (user_id, class_id, test_id, item_id, req_id, version, content,
              usage_count, application_count, *flags)
    
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, values)
                conn.commit()
    except Exception as e:
        raise Exception(f"Failed to add requirement: {e}")

def generate_unique_test_id(base_name, user_id, class_id):
    conn = get_db_connection()
    cur = conn.cursor()

    i = 1
    new_id = f"copy of {base_name}"
    while True:
        cur.execute("""
            SELECT 1 FROM user_tests WHERE user_id = %s AND class_id = %s AND test_id = %s
        """, (user_id, class_id, new_id))

        existing = cur.fetchone()


        if not existing:
            return new_id

        i += 1
        new_id = f"copy ({i}) of {base_name}"

      

if __name__ == "__main__":
    # Define test parameters
    test_user_id = "user1"
    test_class_id = "test_Class"
    test_test_id = "new_structre_test_pt2"

    # Load the test JSON file
    test_file_path = "/Users/joshuayao/Desktop/Harvestor/harvestor-backend/app/utils/test_questions_output.json"
    with open(test_file_path, "r") as f:
        test_data = json.load(f)

    # Call the database insertion function
    print(f"Starting database insertion test with {len(test_data['questions'])} topics.")
    add_to_database(test_user_id, test_class_id, test_test_id, test_data["questions"])
    print("✅ Test completed: Questions inserted into the database.")