from app.database import SessionLocal
from app.models.user import User

def give_credits():
    db = SessionLocal()
    try:
        email = "patelprisha0320@gmail.com"
        
        user = db.query(User).filter(User.email == email).first()
        if not user:
            print(f"❌ User not found: {email}")
            return
        
        user.free_credits_remaining = 100
        db.commit()
        
        print("============================================")
        print(f"✓ Successfully updated credits!")
        print(f"User: {email}")
        print(f"New Credits: {user.free_credits_remaining}")
        print("============================================")

    except Exception as e:
        print("❌ Error:", e)
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    give_credits()
