"""
Database initialization script
Run this to create initial admin user and sample templates
"""
from app.database import SessionLocal, engine, Base
from app.models.user import User, AuthProvider
from app.models.template import Template
from app.utils.security import get_password_hash

def init_database():
    # Create all tables
    Base.metadata.create_all(bind=engine)
    
    db = SessionLocal()
    
    try:
        # Create admin user if not exists
        admin = db.query(User).filter(User.email == "admin@weddingai.com").first()
        if not admin:
            admin = User(
                email="admin@weddingai.com",
                full_name="Admin User",
                hashed_password=get_password_hash("admin123"),  # Change this!
                auth_provider=AuthProvider.EMAIL,
                is_admin=True,
                is_active=True,
                is_verified=True,
                is_subscribed=True,
                credits_remaining=1000
            )
            db.add(admin)
            print("✓ Admin user created")
        
        # Create sample templates
        sample_templates = [
            {
                "name": "Royal Palace Wedding",
                "description": "Transform your photos into a royal palace wedding scene",
                "prompt": "Create a stunning royal palace wedding scene with ornate architecture, elegant lighting, and regal atmosphere. The couple should be dressed in traditional Indian wedding attire.",
                "is_free": True,
                "display_order": 1
            },
            {
                "name": "Beach Sunset Romance",
                "description": "Beautiful beach sunset pre-wedding shoot",
                "prompt": "Create a romantic beach scene at golden hour with gentle waves and sunset backdrop. The couple should appear in elegant casual attire.",
                "is_free": True,
                "display_order": 2
            },
            {
                "name": "Garden Paradise",
                "description": "Lush garden setting with flowers",
                "prompt": "Transform the images into a beautiful garden setting with blooming flowers, natural lighting, and romantic atmosphere.",
                "is_free": False,
                "display_order": 3
            },
            {
                "name": "Mountain Adventure",
                "description": "Adventurous mountain backdrop",
                "prompt": "Create an adventurous pre-wedding shoot in mountains with dramatic landscape and natural beauty.",
                "is_free": False,
                "display_order": 4
            },
            {
                "name": "Vintage Studio",
                "description": "Classic vintage studio photography",
                "prompt": "Transform into a vintage studio photography setting with classic props and timeless aesthetic.",
                "is_free": False,
                "display_order": 5
            },
            {
                "name": "Urban Chic",
                "description": "Modern urban setting",
                "prompt": "Create a modern urban pre-wedding shoot with city architecture and contemporary style.",
                "is_free": False,
                "display_order": 6
            },
            {
                "name": "Traditional Heritage",
                "description": "Traditional Indian heritage setting",
                "prompt": "Transform into a traditional Indian heritage setting with cultural elements and ethnic architecture.",
                "is_free": False,
                "display_order": 7
            },
            {
                "name": "Fairy Tale Castle",
                "description": "Dreamy castle backdrop",
                "prompt": "Create a fairy tale castle setting with dreamy atmosphere and magical lighting.",
                "is_free": False,
                "display_order": 8
            },
            {
                "name": "Desert Dunes",
                "description": "Romantic desert landscape",
                "prompt": "Transform into a romantic desert setting with sand dunes and dramatic lighting.",
                "is_free": False,
                "display_order": 9
            },
            {
                "name": "Forest Fantasy",
                "description": "Enchanted forest setting",
                "prompt": "Create an enchanted forest setting with mystical atmosphere and natural beauty.",
                "is_free": False,
                "display_order": 10
            },
            {
                "name": "Luxury Hotel",
                "description": "Elegant luxury hotel setting",
                "prompt": "Transform into an elegant luxury hotel setting with sophisticated interiors and professional lighting.",
                "is_free": False,
                "display_order": 11
            },
            {
                "name": "Monsoon Romance",
                "description": "Beautiful monsoon backdrop",
                "prompt": "Create a romantic monsoon setting with rain effects and lush greenery.",
                "is_free": False,
                "display_order": 12
            },
            {
                "name": "Royal Fort",
                "description": "Historic fort setting",
                "prompt": "Transform into a historic Indian fort setting with architectural grandeur.",
                "is_free": False,
                "display_order": 13
            },
            {
                "name": "Lavender Fields",
                "description": "Dreamy lavender fields",
                "prompt": "Create a romantic lavender field setting with purple flowers and soft lighting.",
                "is_free": False,
                "display_order": 14
            },
            {
                "name": "Winter Wonderland",
                "description": "Snowy winter scene",
                "prompt": "Transform into a winter wonderland setting with snow and cozy atmosphere.",
                "is_free": False,
                "display_order": 15
            },
            {
                "name": "Cherry Blossom",
                "description": "Japanese cherry blossom setting",
                "prompt": "Create a beautiful cherry blossom setting with pink flowers and serene atmosphere.",
                "is_free": False,
                "display_order": 16
            },
            {
                "name": "Countryside Villa",
                "description": "Rustic countryside villa",
                "prompt": "Transform into a rustic countryside villa setting with pastoral beauty.",
                "is_free": False,
                "display_order": 17
            },
            {
                "name": "Bollywood Glamour",
                "description": "Bollywood style photoshoot",
                "prompt": "Create a glamorous Bollywood-style setting with dramatic lighting and cinematic feel.",
                "is_free": False,
                "display_order": 18
            },
            {
                "name": "Minimalist Modern",
                "description": "Clean minimalist aesthetic",
                "prompt": "Transform into a minimalist modern setting with clean lines and contemporary style.",
                "is_free": False,
                "display_order": 19
            },
            {
                "name": "Festival of Colors",
                "description": "Vibrant Holi celebration theme",
                "prompt": "Create a vibrant Holi celebration setting with colorful atmosphere and joyful mood.",
                "is_free": False,
                "display_order": 20
            }
        ]
        
        for template_data in sample_templates:
            existing = db.query(Template).filter(Template.name == template_data["name"]).first()
            if not existing:
                template = Template(**template_data)
                db.add(template)
        
        db.commit()
        print("✓ Sample templates created")
        print("\n" + "="*50)
        print("Database initialized successfully!")
        print("="*50)
        print("\nAdmin credentials:")
        print("Email: admin@weddingai.com")
        print("Password: admin123")
        print("\nIMPORTANT: Change the admin password after first login!")
        print("="*50)
        
    except Exception as e:
        print(f"Error: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    init_database()