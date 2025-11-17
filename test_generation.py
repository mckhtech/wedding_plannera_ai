#!/usr/bin/env python3
"""
Test script for image generation service
Usage: python test_generation.py
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from app.services.image_generation_service import ImageGenerationService
from app.config import settings
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def test_service_initialization():
    """Test 1: Check if service initializes correctly"""
    logger.info("=" * 60)
    logger.info("TEST 1: Service Initialization")
    logger.info("=" * 60)
    
    try:
        service = ImageGenerationService()
        logger.info("✅ Service initialized successfully")
        
        # Test the service
        result = await service.test_generation()
        logger.info(f"   Model: {result.get('model')}")
        logger.info(f"   Status: {result.get('status')}")
        logger.info(f"   Message: {result.get('message')}")
        
        return True
    except Exception as e:
        logger.error(f"❌ Service initialization failed: {e}")
        return False

async def test_image_generation():
    """Test 2: Generate a test image"""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 2: Image Generation")
    logger.info("=" * 60)
    
    # Check if test images exist
    test_user_image = Path("test_images/user.jpg")
    test_partner_image = Path("test_images/partner.jpg")
    
    if not test_user_image.exists():
        logger.warning("⚠️  Test user image not found at test_images/user.jpg")
        logger.info("   Please create a 'test_images' folder and add test images:")
        logger.info("   - test_images/user.jpg")
        logger.info("   - test_images/partner.jpg (optional)")
        return False
    
    try:
        service = ImageGenerationService()
        
        # Test prompt
        test_prompt = """
        Create a romantic pre-wedding photoshoot image.
        Setting: A beautiful sunset beach scene with golden hour lighting.
        The couple should be walking hand in hand along the shoreline.
        Mood: Romantic, joyful, and natural.
        Style: Professional photography with warm tones and soft focus background.
        """
        
        logger.info("   Generating test image...")
        logger.info(f"   User image: {test_user_image}")
        
        partner_path = str(test_partner_image) if test_partner_image.exists() else None
        if partner_path:
            logger.info(f"   Partner image: {test_partner_image}")
        else:
            logger.info("   Partner image: None (single person mode)")
        
        generated_path, watermarked_path = await service.generate_image(
            user_image_path=str(test_user_image),
            partner_image_path=partner_path,
            prompt=test_prompt,
            add_watermark=True
        )
        
        logger.info(f"✅ Image generated successfully!")
        logger.info(f"   Generated image: {generated_path}")
        if watermarked_path:
            logger.info(f"   Watermarked image: {watermarked_path}")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Image generation failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def main():
    """Run all tests"""
    logger.info("\n🎨 WEDDING IMAGE GENERATOR - TEST SUITE")
    logger.info("=" * 60)
    
    # Check configuration
    logger.info("\nConfiguration Check:")
    logger.info(f"   GEMINI_API_KEY: {'✅ Set' if settings.GEMINI_API_KEY else '❌ Not set'}")
    logger.info(f"   UPLOAD_DIR: {settings.UPLOAD_DIR}")
    logger.info(f"   GENERATED_DIR: {settings.GENERATED_DIR}")
    logger.info(f"   TEMPLATE_PREVIEW_DIR: {settings.TEMPLATE_PREVIEW_DIR}")
    
    if not settings.GEMINI_API_KEY:
        logger.error("\n❌ GEMINI_API_KEY is not set in .env file!")
        logger.info("   Please add: GEMINI_API_KEY=your_api_key_here")
        return
    
    # Run tests
    results = []
    
    # Test 1: Service initialization
    results.append(await test_service_initialization())
    
    # Test 2: Image generation (only if test images exist)
    results.append(await test_image_generation())
    
    # Summary
    logger.info("\n" + "=" * 60)
    logger.info("TEST SUMMARY")
    logger.info("=" * 60)
    passed = sum(results)
    total = len(results)
    logger.info(f"   Passed: {passed}/{total}")
    
    if passed == total:
        logger.info("   ✅ All tests passed!")
    else:
        logger.info("   ⚠️  Some tests failed")
    
    logger.info("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())