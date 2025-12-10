#!/usr/bin/env python3
"""Script to create or promote a user to admin"""

from app.database import SessionLocal
from app.models.user import User, AuthProvider
from app.utils.security import get_password_hash

def create_admin(email: str, password: str, full_name: str = "Admin User"):
    """Create a new admin user"""
    db = SessionLocal()
    
    try:
        # Check if user already exists
        existing_user = db.query(User).filter(User.email == email).first()
        
        if existing_user:
            # Make existing user admin
            existing_user.is_admin = True
            existing_user.is_active = True
            existing_user.is_verified = True
            db.commit()
            print(f"✅ User '{email}' promoted to admin!")
            print(f"   User ID: {existing_user.id}")
            print(f"   Is Admin: {existing_user.is_admin}")
        else:
            # Create new admin user
            hashed_password = get_password_hash(password)
            admin_user = User(
                email=email,
                full_name=full_name,
                hashed_password=hashed_password,
                auth_provider=AuthProvider.EMAIL,
                is_admin=True,
                is_active=True,
                is_verified=True,
                credits_remaining=100  # Give admin some credits
            )
            
            db.add(admin_user)
            db.commit()
            db.refresh(admin_user)
            
            print(f"✅ Admin user created successfully!")
            print(f"   Email: {admin_user.email}")
            print(f"   User ID: {admin_user.id}")
            print(f"   Is Admin: {admin_user.is_admin}")
        
        print(f"\n🔑 You can now login with:")
        print(f"   Email: {email}")
        print(f"   Password: {password}")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) >= 3:
        email = sys.argv[1]
        password = sys.argv[2]
        full_name = sys.argv[3] if len(sys.argv) > 3 else "Admin User"
        create_admin(email, password, full_name)
    else:
        print("Usage: python create_admin.py <email> <password> [full_name]")
        print("\nOr run interactively:")
        email = input("Enter admin email: ")
        password = input("Enter admin password: ")
        full_name = input("Enter full name (or press Enter for 'Admin User'): ") or "Admin User"
        create_admin(email, password, full_name)