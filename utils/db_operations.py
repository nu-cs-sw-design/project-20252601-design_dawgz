import psycopg2
import uuid
from dotenv import load_dotenv
import os
import json
from sqlalchemy import text


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
    """
    Get the highest topic_id from item_topics for a given user_id and class_id.
    
    Args:
        user_id (str): The user's ID
        class_id (str): The class ID
        
    Returns:
        str or None: The highest topic_id, or None if no topics exist
    """
    if isinstance(db_session, psycopg2.extensions.cursor):
        db_session.execute("""
            SELECT topic_id FROM item_topics
            WHERE user_id = %s AND class_id = %s
            ORDER BY topic_id DESC LIMIT 1
        """, (user_id, class_id))
        result = db_session.fetchone()
        return result[0] if result else None
    else:
        result = db_session.execute(
            text("""
                SELECT topic_id FROM item_topics
                WHERE user_id = :user_id AND class_id = :class_id
                ORDER BY topic_id DESC LIMIT 1
            """),
            {
                "user_id": user_id,
                "class_id": class_id
            }
        ).fetchone()
        return result[0] if result else None


def insert_item_current(db_session, user_id, class_id, item_id, version):
    """
    Insert a record into item_current table.
    
    Args:
        user_id (str): The user's ID
        class_id (str): The class ID
        item_id (str): The item ID
        version (int): The version number
        
    Returns:
        None
    """
    db_session.execute(
        text("""
            INSERT INTO item_current (user_id, class_id, item_id, version)
            VALUES (:user_id, :class_id, :item_id, :version)
        """),
        {
            "user_id": user_id,
            "class_id": class_id,
            "item_id": item_id,
            "version": version
        }
    )


def insert_item_history(db_session, user_id, class_id, item_id, version, question, answer_part, question_type, difficulty, wrong_answer_explanation):
    """
    Insert a record into item_current table.
    
    Args:
        user_id (str): The user's ID
        class_id (str): The class ID
        item_id (str): The item ID
        version (int): The version number
        question (str): The question part
        answer_part (str): The answer part
        question_type (str): The question type
        difficulty (str): The difficulty
        wrong_answer_explanation (str): The wrong answer explanation
        
    Returns:
        None
    """
    db_session.execute(
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


def insert_item_topics(db_session, user_id, class_id, item_id, version, topic_id, topic_name):
    db_session.execute(
        text(
            """
            INSERT INTO item_topics 
            (user_id, class_id, item_id, version, topic_id, topic_name)
            VALUES (:user_id, :class_id, :item_id, :version, :topic_id, :topic_name)
            """
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


def insert_item_skills(db_session, user_id, class_id, item_id, version, skill_id, skill_name):
     db_session.execute(
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


def insert_tests(db_session, user_id, class_id, test_id, item_id, order_number):
    db_session.execute(
        text(
            """
            INSERT INTO tests (user_id, class_id, test_id, item_id, order_number)
            VALUES (:user_id, :class_id, :testid, :item_id, :order_number)
            """
        ),
        {
            "user_id": user_id,
            "class_id": class_id,
            "testid": test_id,
            "item_id": item_id,
            "order_number": order_number,
        },
    )
 

def select_unique_class(db_session, user_id, class_id):
    existing_class = db_session.execute(
        text(
            "SELECT 1 FROM user_classes WHERE user_id = :user_id AND class_id = :class_id"
        ),
        {"user_id": user_id, "class_id": class_id},
    ).fetchone()
    if not existing_class:
            db_session.execute(
                text(
                "INSERT INTO user_classes (user_id, class_id) VALUES (:user_id, :class_id)"
                ),
                {"user_id": user_id, "class_id": class_id},
            )


def select_topic_id(db_session, userid, classid):
    
    db_session.execute(
        text(
            """
            SELECT topic_id FROM item_topics
            WHERE user_id = :user_id AND class_id = :class_id
            ORDER BY topic_id DESC LIMIT 1
        """
        ),
        {"user_id": userid, "class_id": classid},
    )


def select_skill_id(db_session, userid, classid):
    
    db_session.execute(
        text(
            """
            SELECT topic_id FROM item_skills
            WHERE user_id = :user_id AND class_id = :class_id
            ORDER BY topic_id DESC LIMIT 1
        """
        ),
        {"user_id": userid, "class_id": classid},
    )


def add_to_database(user_id, class_id, test_id, questions, order_number=None):
    """
    Save structured questions into the database.

    Args:
        user_id (str): The user's ID.
        class_id (str): The class ID.
        test_id (str): The test ID for this batch of questions.
        questions (list): List of questions with metadata.
        order_number (int, optional): The desired order number for the new item(s).
    """
    conn = get_db_connection()
    cur = conn.cursor()

    try:
        # Ensure user-class relationship exists
        cur.execute("""
            SELECT 1 FROM user_classes WHERE user_id = %s AND class_id = %s
        """, (user_id, class_id))
        existing_class = cur.fetchone()

        if not existing_class:
            cur.execute("""
                INSERT INTO user_classes (user_id, class_id) VALUES (%s, %s)
            """, (user_id, class_id))

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
                cur.execute("""
                    INSERT INTO item_current (user_id, class_id, item_id, version)
                    VALUES (%s, %s, %s, %s)
                """, (user_id, class_id, item_id, version))

                # Insert into item_history
                cur.execute("""
                    INSERT INTO item_history (user_id, class_id, item_id, version, question_part, answer_part, format, difficulty, wrong_answer_explanation)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    user_id, class_id, item_id, version,
                    formatted_question_part, answer_part,
                    format_type, difficulty, wrong_answer_explanation if wrong_answer_explanation else None
                ))

                # Insert into item_topics
                for related_topic in question.get("relatedtopics", []):
                    related_topic_id = f"{related_topic.replace(' ', '_')}_{class_id}"
                    cur.execute("""
                        INSERT INTO item_topics (user_id, class_id, item_id, version, topic_id, topic_name)
                        VALUES (%s, %s, %s, %s, %s, %s)
                    """, (user_id, class_id, item_id, version, related_topic_id, related_topic))

                # Insert into item_skills
                for skill_name in question.get("relatedskills", []):
                    skill_id = f"{skill_name.replace(' ', '_')}_{class_id}"
                    cur.execute("""
                        INSERT INTO item_skills (user_id, class_id, item_id, version, skill_id, skill_name)
                        VALUES (%s, %s, %s, %s, %s, %s)
                    """, (user_id, class_id, item_id, version, skill_id, skill_name))

                new_order = fetch_next_order_number(cur, user_id, class_id, test_id, order_number)

                # Link each question to the test in the `tests` table
                cur.execute("""
                    INSERT INTO tests (user_id, class_id, test_id, item_id, order_number)
                    VALUES (%s, %s, %s, %s, %s)
                """, (user_id, class_id, test_id, item_id, new_order))

        # Commit transaction
        conn.commit()

    except Exception as e:
        conn.rollback()
        raise Exception(f"Database operation failed: {e}")
    
    finally:
        cur.close()
        conn.close()


def fetch_item_latest_version(user_id, class_id, item_id):
    conn = get_db_connection()
    cur = conn.cursor()
        
    try:
        # Get the latest version of the item
        cur.execute("""
            SELECT version FROM item_current
            WHERE user_id = %s AND class_id = %s AND item_id = %s
        """, (user_id, class_id, item_id))
        latest_version = cur.fetchone()
        

        if latest_version:
            return latest_version[0]
        else:
            raise Exception("Item not found")
    except Exception as e:
        raise Exception(f"Failed to fetch latest version: {e}")
    
    finally:
        cur.close()
        conn.close()
      
  
def fetch_item_data(user_id, class_id, item_id, version):
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        # Get the item details from item_history
        cur.execute("""
            SELECT question_part, answer_part, format, difficulty, wrong_answer_explanation 
            FROM item_history
            WHERE user_id = %s AND class_id = %s AND item_id = %s AND version = %s
        """, (user_id, class_id, item_id, version))
        item_data = cur.fetchone()
        
        if not item_data: raise Exception("Item not found in history.")
        
        # Get item topics from item_topics
        cur.execute("""
            SELECT topic_name 
            FROM item_topics
            WHERE user_id = %s AND class_id = %s AND item_id = %s AND version = %s
        """, (user_id, class_id, item_id, version))
        item_topics = cur.fetchall()
        
        item_topics = [topic[0] for topic in item_topics]
        
        # Get item skills form item_skills
        cur.execute("""
            SELECT skill_name
            FROM item_skills
            WHERE user_id = %s AND class_id = %s  AND item_id = %s AND version = %s
        """, (user_id, class_id, item_id, version))
        item_skills = cur.fetchall()
        
        item_skills = [skill[0] for skill in item_skills]
        
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
    
    finally:
        cur.close()
        conn.close()


def add_requirement_to_database(user_id, class_id, test_id, item_id, req_id, version, content, usage_count, application_count, contentType):
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