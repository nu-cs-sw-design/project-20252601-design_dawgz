# GPT Routes Module

This directory contains modular GPT-related routes, organized by functionality.

## Structure

```
gpt/
├── __init__.py                      # Exports gpt_bp and imports all route modules
├── gpt_blueprint.py                 # Defines the main gpt_bp Blueprint
├── topic_generation_routes.py      # Topic-based question generation
├── modification_routes.py           # Item modification and editing
├── content_upload_routes.py         # Syllabus and PDF processing
├── similar_generation_routes.py     # Similar question generation
├── image_generation_routes.py       # Image-based question generation
├── requirement_routes.py            # Requirements application and generation
└── README.md                        # This file
```

## Usage

The main `gpt_bp` blueprint is imported in `gpt_routes.py` and registered with the Flask app.
All routes from the old monolithic file have been successfully migrated to modular files.

### Adding New Routes

1. Determine the appropriate file for your route (or create a new one)
2. Import the blueprint: `from .gpt_blueprint import gpt_bp`
3. Define your routes using `@gpt_bp.route(...)`
4. Import the module in `__init__.py`: `from . import your_new_routes`

## Route Organization

### topic_generation_routes.py
- `POST /generate_multiple_items` - Generate multiple MC/FR questions based on topics and formats (GPT-5 migrated)

### modification_routes.py
- `POST /modify-item` - Modify an existing item using GPT
- `POST /edit-item-component` - Edit specific components of an item

### content_upload_routes.py
- `POST /process_syllabus` - Process syllabus PDFs and generate questions
- `POST /pdf_upload` - Upload and process PDF/image files for question extraction

### similar_generation_routes.py
- `POST /generate_similar` - Generate questions similar to an existing item

### image_generation_routes.py
- `POST /image_upload` - Upload images and extract questions
- `POST /generate_from_image` - Generate questions from a single image

### requirement_routes.py
- `POST /apply-requirements` - Apply requirements to items
- `POST /generate-requirement` - Generate requirements from item modifications
