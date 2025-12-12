"""
Test script to verify AWS RDS and S3 connections
Run this before deploying to EC2
"""

import sys
import os
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from app.config import settings
from app.database import engine, SessionLocal, check_db_connection
from app.services.s3_service import s3_service
from sqlalchemy import text
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_rds_connection():
    """Test RDS PostgreSQL connection"""
    print("\n" + "="*60)
    print("🗄️  TESTING RDS DATABASE CONNECTION")
    print("="*60)
    
    try:
        print(f"Database URL: {settings.DATABASE_URL[:30]}...")
        
        # Test basic connection
        if check_db_connection():
            print("✅ Database connection successful!")
        else:
            print("❌ Database connection failed!")
            return False
        
        # Test query execution
        db = SessionLocal()
        result = db.execute(text("SELECT version();"))
        version = result.fetchone()[0]
        print(f"✅ PostgreSQL Version: {version[:50]}...")
        
        # Test table access
        result = db.execute(text("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public';"))
        table_count = result.fetchone()[0]
        print(f"✅ Found {table_count} tables in database")
        
        db.close()
        return True
        
    except Exception as e:
        print(f"❌ Database test failed: {str(e)}")
        return False

def test_s3_connection():
    """Test S3 connection and permissions"""
    print("\n" + "="*60)
    print("☁️  TESTING S3 CONNECTION")
    print("="*60)
    
    if not settings.USE_S3:
        print("ℹ️  S3 is disabled (USE_S3=false)")
        return True
    
    try:
        print(f"Bucket: {settings.S3_BUCKET_NAME}")
        print(f"Region: {settings.AWS_REGION}")
        
        # Test connection
        if s3_service.test_connection():
            print("✅ S3 connection successful!")
        else:
            print("❌ S3 connection failed!")
            return False
        
        # Test upload
        print("\n📤 Testing file upload...")
        test_file_path = Path("test_upload.txt")
        test_file_path.write_text("Test file for S3 upload")
        
        s3_url = s3_service.upload_file(
            file_path=str(test_file_path),
            s3_key="test/test_upload.txt"
        )
        print(f"✅ Upload successful: {s3_url}")
        
        # Test file existence
        print("\n🔍 Testing file existence check...")
        if s3_service.file_exists(s3_url):
            print("✅ File exists in S3")
        else:
            print("❌ File not found in S3")
            return False
        
        # Test deletion
        print("\n🗑️  Testing file deletion...")
        if s3_service.delete_file(s3_url):
            print("✅ File deleted successfully")
        else:
            print("❌ File deletion failed")
            return False
        
        # Cleanup local test file
        test_file_path.unlink()
        
        return True
        
    except Exception as e:
        print(f"❌ S3 test failed: {str(e)}")
        return False

def test_environment_variables():
    """Verify all required environment variables are set"""
    print("\n" + "="*60)
    print("🔧 CHECKING ENVIRONMENT VARIABLES")
    print("="*60)
    
    required_vars = {
        "DATABASE_URL": settings.DATABASE_URL,
        "SECRET_KEY": settings.SECRET_KEY,
        "GEMINI_API_KEY": settings.GEMINI_API_KEY,
        "FRONTEND_URL": settings.FRONTEND_URL,
        "BACKEND_URL": settings.BACKEND_URL,
    }
    
    if settings.USE_S3:
        required_vars.update({
            "AWS_ACCESS_KEY_ID": settings.AWS_ACCESS_KEY_ID,
            "AWS_SECRET_ACCESS_KEY": settings.AWS_SECRET_ACCESS_KEY,
            "S3_BUCKET_NAME": settings.S3_BUCKET_NAME,
        })
    
    all_set = True
    for var_name, var_value in required_vars.items():
        if var_value:
            # Mask sensitive values
            if "KEY" in var_name or "SECRET" in var_name or "PASSWORD" in var_name:
                display_value = f"{str(var_value)[:5]}...{str(var_value)[-5:]}"
            else:
                display_value = str(var_value)[:50] + ("..." if len(str(var_value)) > 50 else "")
            
            print(f"✅ {var_name}: {display_value}")
        else:
            print(f"❌ {var_name}: NOT SET")
            all_set = False
    
    return all_set

def run_all_tests():
    """Run all connection tests"""
    print("\n" + "="*60)
    print("🧪 AWS CONNECTION TEST SUITE")
    print("="*60)
    
    results = {
        "Environment Variables": test_environment_variables(),
        "RDS Database": test_rds_connection(),
        "S3 Storage": test_s3_connection()
    }
    
    print("\n" + "="*60)
    print("📊 TEST RESULTS SUMMARY")
    print("="*60)
    
    for test_name, passed in results.items():
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"{test_name}: {status}")
    
    all_passed = all(results.values())
    
    if all_passed:
        print("\n🎉 All tests passed! Your AWS setup is ready.")
        print("\n📝 Next steps:")
        print("   1. Update your .env with the RDS endpoint and S3 credentials")
        print("   2. Set USE_S3=true in .env to enable S3")
        print("   3. Run your FastAPI server: uvicorn app.main:app --reload")
        print("   4. Test image upload and generation through your API")
    else:
        print("\n⚠️  Some tests failed. Please fix the issues before proceeding.")
        print("\n🔍 Common issues:")
        print("   - RDS: Check security group allows your IP on port 5432")
        print("   - RDS: Verify endpoint, username, and password are correct")
        print("   - S3: Check IAM user has S3FullAccess policy")
        print("   - S3: Verify bucket name and region are correct")
        print("   - S3: Check AWS credentials are set correctly")
    
    return all_passed

if __name__ == "__main__":
    try:
        success = run_all_tests()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Unexpected error: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)