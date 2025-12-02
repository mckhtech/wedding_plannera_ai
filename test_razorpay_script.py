"""
Standalone test script for Razorpay integration
Run this from your backend directory: python test_razorpay_script.py

This script tests:
1. Razorpay credential validation
2. Full payment flow (create order → verify)
3. Token generation for paid templates
"""

import requests
import json
import time
from typing import Dict, Any

# ============================================
# CONFIGURATION
# ============================================
BASE_URL = "http://127.0.0.1:8000"  # Change if your backend runs on different port
TEST_USER_EMAIL = "usernew@example.com"  # Change to your test user
TEST_USER_PASSWORD = "password@123"  # Change to your test user password
PAID_TEMPLATE_ID = 3  # Your paid template ID


class RazorpayTester:
    def __init__(self):
        self.base_url = BASE_URL
        self.token = None
        self.user_info = None
        
    def print_section(self, title: str):
        """Print a section header"""
        print("\n" + "="*60)
        print(f"  {title}")
        print("="*60)
    
    def print_result(self, success: bool, message: str, data: Any = None):
        """Print a test result"""
        icon = "✅" if success else "❌"
        print(f"\n{icon} {message}")
        if data:
            print(json.dumps(data, indent=2))
    
    def login(self) -> bool:
        """Login and get access token"""
        self.print_section("Step 1: Authentication")
        
        try:
            response = requests.post(
                f"{self.base_url}/api/auth/login",
                json={
                    "email": TEST_USER_EMAIL,
                    "password": TEST_USER_PASSWORD
                }
            )
            
            if response.status_code == 200:
                data = response.json()
                self.token = data["access_token"]
                self.print_result(True, "Login successful", {"token": self.token[:20] + "..."})
                return True
            else:
                self.print_result(False, f"Login failed: {response.status_code}", response.json())
                return False
                
        except Exception as e:
            self.print_result(False, f"Login error: {str(e)}")
            return False
    
    def get_headers(self) -> Dict[str, str]:
        """Get authorization headers"""
        return {"Authorization": f"Bearer {self.token}"}
    
    def test_credentials(self) -> bool:
        """Test if Razorpay credentials are valid"""
        self.print_section("Step 2: Test Razorpay Credentials")
        
        try:
            response = requests.get(
                f"{self.base_url}/api/test/razorpay/credentials"
            )
            
            if response.status_code == 200:
                data = response.json()
                self.print_result(True, "Razorpay credentials valid", data)
                return data.get("valid", False)
            else:
                self.print_result(False, "Credential test failed", response.json())
                return False
                
        except Exception as e:
            self.print_result(False, f"Credential test error: {str(e)}")
            return False
    
    def get_user_credits(self) -> bool:
        """Get user credit information"""
        self.print_section("Step 3: Check User Credits")
        
        try:
            response = requests.get(
                f"{self.base_url}/api/auth/me/credits",
                headers=self.get_headers()
            )
            
            if response.status_code == 200:
                self.user_info = response.json()
                self.print_result(True, "User credits retrieved", self.user_info)
                return True
            else:
                self.print_result(False, "Failed to get credits", response.json())
                return False
                
        except Exception as e:
            self.print_result(False, f"Credit check error: {str(e)}")
            return False
    
    def test_payment_flow(self) -> bool:
        """Test complete payment flow"""
        self.print_section("Step 4: Test Full Payment Flow")
        
        try:
            response = requests.post(
                f"{self.base_url}/api/test/payment/full-flow",
                headers=self.get_headers(),
                json={"template_id": PAID_TEMPLATE_ID}
            )
            
            if response.status_code == 200:
                data = response.json()
                self.print_result(True, "Payment flow completed", data)
                return True
            else:
                self.print_result(False, "Payment flow failed", response.json())
                return False
                
        except Exception as e:
            self.print_result(False, f"Payment flow error: {str(e)}")
            return False
    
    def check_template_access(self) -> bool:
        """Check if user can now access the paid template"""
        self.print_section("Step 5: Check Template Access")
        
        try:
            response = requests.get(
                f"{self.base_url}/api/payment/check-access/{PAID_TEMPLATE_ID}",
                headers=self.get_headers()
            )
            
            if response.status_code == 200:
                data = response.json()
                self.print_result(True, "Template access checked", data)
                
                if data.get("can_generate"):
                    print("\n🎉 SUCCESS: You can now generate images with this template!")
                else:
                    print("\n⚠️ WARNING: Cannot generate yet. Reason:", data.get("reason"))
                
                return data.get("can_generate", False)
            else:
                self.print_result(False, "Access check failed", response.json())
                return False
                
        except Exception as e:
            self.print_result(False, f"Access check error: {str(e)}")
            return False
    
    def get_my_tokens(self) -> bool:
        """Get list of payment tokens"""
        self.print_section("Step 6: View My Payment Tokens")
        
        try:
            response = requests.get(
                f"{self.base_url}/api/test/payment/my-test-tokens",
                headers=self.get_headers()
            )
            
            if response.status_code == 200:
                data = response.json()
                self.print_result(True, f"Found {data['total_tokens']} tokens", data)
                return True
            else:
                self.print_result(False, "Failed to get tokens", response.json())
                return False
                
        except Exception as e:
            self.print_result(False, f"Token fetch error: {str(e)}")
            return False
    
    def run_all_tests(self):
        """Run complete test suite"""
        print("\n")
        print("╔" + "="*58 + "╗")
        print("║" + " "*15 + "RAZORPAY TEST SUITE" + " "*24 + "║")
        print("╚" + "="*58 + "╝")
        
        results = []
        
        # Test 1: Login
        if not self.login():
            print("\n❌ FAILED: Cannot proceed without authentication")
            return
        results.append(True)
        
        # Test 2: Credentials
        results.append(self.test_credentials())
        
        # Test 3: User credits
        results.append(self.get_user_credits())
        
        # Test 4: Payment flow
        results.append(self.test_payment_flow())
        
        # Test 5: Template access
        results.append(self.check_template_access())
        
        # Test 6: View tokens
        results.append(self.get_my_tokens())
        
        # Summary
        self.print_section("TEST SUMMARY")
        passed = sum(results)
        total = len(results)
        
        print(f"\n{'='*60}")
        print(f"Tests Passed: {passed}/{total}")
        print(f"Success Rate: {(passed/total)*100:.1f}%")
        print(f"{'='*60}\n")
        
        if passed == total:
            print("🎉 ALL TESTS PASSED! Your Razorpay integration is working!")
        else:
            print("⚠️ Some tests failed. Check the output above for details.")


# ============================================
# ADDITIONAL UTILITY FUNCTIONS
# ============================================

def test_create_order_only():
    """Test only order creation (useful for production mode)"""
    tester = RazorpayTester()
    
    if not tester.login():
        return
    
    tester.print_section("Create Razorpay Order (Production Test)")
    
    try:
        response = requests.post(
            f"{tester.base_url}/api/test/payment/create-order-only",
            headers=tester.get_headers(),
            json={"template_id": PAID_TEMPLATE_ID}
        )
        
        if response.status_code == 200:
            data = response.json()
            tester.print_result(True, "Order created successfully", data)
            
            if not data['order'].get('test_mode', True):
                print("\n📝 NEXT STEPS (Production Mode):")
                print(f"1. Order ID: {data['order']['order_id']}")
                print(f"2. Amount: {data['order']['currency']} {data['order']['amount']}")
                print("3. Go to Razorpay Dashboard → Test Payments")
                print("4. Complete the payment")
                print("5. Use /api/test/payment/verify-manual to verify")
        else:
            tester.print_result(False, "Order creation failed", response.json())
            
    except Exception as e:
        tester.print_result(False, f"Error: {str(e)}")


# ============================================
# MAIN EXECUTION
# ============================================

if __name__ == "__main__":
    import sys
    
    print("\n🚀 Starting Razorpay Integration Tests...\n")
    
    # Check if we want specific test
    if len(sys.argv) > 1:
        if sys.argv[1] == "order":
            test_create_order_only()
        else:
            print("Usage: python test_razorpay_script.py [order]")
    else:
        # Run full test suite
        tester = RazorpayTester()
        tester.run_all_tests()
    
    print("\n✨ Testing complete!\n")