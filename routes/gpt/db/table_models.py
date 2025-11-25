# table_models.py
# Description: Defines the ORM models for database tables.

from app import db

class UserClasses(db.Model):
    __tablename__ = 'user_classes'
    
    user_id = db.Column(db.String(255), primary_key=True)
    class_id = db.Column(db.String(255), primary_key=True)
    class_description = db.Column(db.String(255), nullable=True)
    class_color = db.Column(db.String(50), nullable=True)

    def to_dict(self):
        """Converts the model instance to a dictionary for JSON serialization."""
        return {
            "classId": self.class_id,
            "description": self.class_description,
            "color": self.class_color
        }
        
class UserTests(db.Model):
    __tablename__ = 'user_tests'

    user_id = db.Column(db.String(255), primary_key=True)
    class_id = db.Column(db.String(255), primary_key=True)
    test_id = db.Column(db.String(255), primary_key=True)

class ItemCurrent(db.Model):
    __tablename__ = 'item_current'

    user_id = db.Column(db.String(255), primary_key=True)
    class_id = db.Column(db.String(255), primary_key=True)
    item_id = db.Column(db.String(255), primary_key=True)
    version = db.Column(db.Integer)

class ItemHistory(db.Model):
    __tablename__ = 'item_history'

    user_id = db.Column(db.String(255), primary_key=True)
    class_id = db.Column(db.String(255), primary_key=True)
    item_id = db.Column(db.String(255), primary_key=True)
    version = db.Column(db.Integer, primary_key=True)
    question_part = db.Column(db.Text)
    answer_part = db.Column(db.Text)
    format = db.Column(db.String(255))
    difficulty = db.Column(db.String(50))
    wrong_answer_explanation = db.Column(db.Text)
        
class Tests(db.Model):
    __tablename__ = 'tests'

    user_id = db.Column(db.String(255), primary_key=True)
    class_id = db.Column(db.String(255), primary_key=True)
    test_id = db.Column(db.String(255), primary_key=True)
    item_id = db.Column(db.String(255), primary_key=True)
    order_number = db.Column(db.Integer, nullable=True)
    
class ItemTopics(db.Model):
    __tablename__ = 'item_topics'
    user_id = db.Column(db.String(255), primary_key=True)
    class_id = db.Column(db.String(255), primary_key=True)
    item_id = db.Column(db.String(255), primary_key=True)
    version = db.Column(db.Integer, primary_key=True)
    topic_id = db.Column(db.String(255), primary_key=True)
    topic_name = db.Column(db.String(255))

class ItemSkills(db.Model):
    __tablename__ = 'item_skills'
    user_id = db.Column(db.String(255), primary_key=True)
    class_id = db.Column(db.String(255), primary_key=True)
    item_id = db.Column(db.String(255), primary_key=True)
    version = db.Column(db.Integer, primary_key=True)
    skill_id = db.Column(db.String(255), primary_key=True)
    skill_name = db.Column(db.String(255))
    
class Requirements(db.Model):
    __tablename__ = 'requirements'
    user_id = db.Column(db.String(255), primary_key=True)
    class_id = db.Column(db.String(255), primary_key=True)
    test_id = db.Column(db.String(255), primary_key=True)
    item_id = db.Column(db.String(255))
    req_id = db.Column(db.String(255), primary_key=True)
    version = db.Column(db.Integer)
    content = db.Column(db.Text)
    usage_count = db.Column(db.Integer)
    application_count = db.Column(db.Integer)
    question = db.Column(db.Boolean)
    answer = db.Column(db.Boolean)
    wrong_answer_explanation = db.Column(db.Boolean)
    topics = db.Column(db.Boolean)
    skills = db.Column(db.Boolean)
    
    def to_dict(self):
        """Converts the model instance to a dictionary for JSON serialization."""
        return {
            "requirementId": self.req_id,
            "requirementName": self.content,
            "usageCount": self.usage_count,
            "applicationCount": self.application_count,
            "question": self.question,
            "answer": self.answer,
            "explanation": self.wrong_answer_explanation,
            "topics": self.topics,
            "skills": self.skills
        }