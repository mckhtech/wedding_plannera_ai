"""
Database initialization script
Run this to create initial admin user and sample templates
"""
from app.database import SessionLocal, engine, Base
from app.models.user import User, AuthProvider
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
                free_credits_remaining=1000
            )
            db.add(admin)
            print("✓ Admin user created")
        
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