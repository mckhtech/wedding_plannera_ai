import logging
from google import genai
from google.genai import types
from pathlib import Path
import uuid
from app.config import settings
from app.services.watermark_service import WatermarkService
from PIL import Image
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

class ImageGenerationService:
    def __init__(self):
        """Initialize Gemini client for image generation"""
        if not settings.GEMINI_API_KEY:
            logger.error("GEMINI_API_KEY not configured")
            raise ValueError("GEMINI_API_KEY is required")
            
        self.api_key = settings.GEMINI_API_KEY
        self.model_name = "gemini-2.5-flash-image"
        logger.info(f"Image Generation Service initialized with model: {self.model_name}")
    
    async def generate_image(
        self, 
        user_image_path: str,
        partner_image_path: Optional[str] = None,
        prompt: str = "",
        add_watermark: bool = False
    ) -> Tuple[str, Optional[str]]:
        """
        Generate image using Gemini API
        
        Args:
            user_image_path: Path to user's image
            partner_image_path: Path to partner's image (optional)
            prompt: Template prompt for image generation
            add_watermark: Whether to add watermark to generated image
            
        Returns:
            Tuple[str, Optional[str]]: (generated_image_path, watermarked_image_path)
            
        Raises:
            Exception: If image generation fails
        """
        try:
            logger.info("Starting image generation")
            logger.debug(f"User image: {user_image_path}")
            logger.debug(f"Partner image: {partner_image_path}")
            logger.debug(f"Add watermark: {add_watermark}")
            
            # Validate and load images
            user_path = self._validate_and_get_path(user_image_path, "User")
            partner_path = None
            if partner_image_path:
                partner_path = self._validate_and_get_path(partner_image_path, "Partner")
            
            # Create generation prompt
            full_prompt = self._create_generation_prompt(prompt, has_partner=partner_path is not None)
            logger.debug(f"Prompt created (length: {len(full_prompt)} chars)")
            
            # Initialize Gemini client
            client = genai.Client(api_key=self.api_key)
            
            # Load images
            user_image = Image.open(user_path)
            logger.debug(f"User image loaded: {user_image.size}")
            
            contents = [full_prompt, user_image]
            
            if partner_path:
                partner_image = Image.open(partner_path)
                logger.debug(f"Partner image loaded: {partner_image.size}")
                contents.append(partner_image)
            
            # Configure generation
            config = types.GenerateContentConfig(
                response_modalities=["IMAGE"],
                image_config=types.ImageConfig(aspect_ratio="1:1")
            )
            
            logger.info("Sending request to Gemini API")
            
            # Generate image
            response = client.models.generate_content(
                model=self.model_name,
                contents=contents,
                config=config
            )
            
            logger.info("Gemini API response received")
            
            # Save generated image
            generated_path = self._save_generated_image(response)
            
            # Add watermark if requested
            watermarked_path = None
            if add_watermark:
                watermarked_path = self._add_watermark(generated_path)
            
            logger.info("Image generation completed successfully")
            return str(generated_path), watermarked_path
            
        except FileNotFoundError as e:
            logger.error(f"File not found: {str(e)}")
            raise Exception(f"Image file not found: {str(e)}")
        except Exception as e:
            logger.error(f"Image generation failed: {str(e)}", exc_info=True)
            raise Exception(f"Image generation failed: {str(e)}")
    
    def _validate_and_get_path(self, file_path: str, label: str) -> Path:
        """Validate file exists and return Path object"""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"{label} image not found at: {file_path}")
        
        logger.debug(f"{label} image exists: {path.stat().st_size} bytes")
        return path
    
    def _save_generated_image(self, response) -> Path:
        """Save generated image from API response"""
        if not response.candidates or not response.candidates[0].content.parts:
            raise Exception("No valid response from Gemini API")
        
        part = response.candidates[0].content.parts[0]
        if not hasattr(part, 'inline_data') or not part.inline_data:
            raise Exception("No inline image data found in response")
        
        # Create output directory
        generated_dir = Path(settings.GENERATED_DIR)
        generated_dir.mkdir(parents=True, exist_ok=True)
        
        # Save image
        generated_filename = f"{uuid.uuid4()}.png"
        generated_path = generated_dir / generated_filename
        
        generated_image = part.as_image()
        generated_image.save(str(generated_path))
        
        logger.info(f"Image saved: {generated_path}")
        return generated_path
    
    def _add_watermark(self, image_path: Path) -> str:
        """Add watermark to generated image"""
        try:
            generated_dir = Path(settings.GENERATED_DIR)
            watermarked_filename = f"{uuid.uuid4()}_watermarked.png"
            watermarked_path = str(generated_dir / watermarked_filename)
            
            WatermarkService.add_watermark(
                str(image_path),
                watermarked_path,
                settings.WATERMARK_TEXT
            )
            
            logger.info(f"Watermark added: {watermarked_path}")
            return watermarked_path
            
        except Exception as e:
            logger.error(f"Watermark addition failed: {str(e)}")
            # Return original path if watermarking fails
            return str(image_path)
    
    def _create_generation_prompt(self, template_prompt: str, has_partner: bool = False) -> str:
        """Create comprehensive prompt for image generation"""
        
        base_prompt = """You are an expert AI image generator specializing in photorealistic portraits.
Your PRIMARY OBJECTIVE is to maintain EXACT facial accuracy from the reference images provided.
This is a professional pre-wedding photoshoot that must preserve the individuals' unique features."""
        
        if has_partner:
            people_description = """
CRITICAL INSTRUCTIONS FOR FACIAL ACCURACY:
- Person 1 and Person 2 are provided in separate images
- You MUST maintain their EXACT facial features, including:
  * Face shape and bone structure
  * Eye shape, color, and spacing
  * Nose shape and size
  * Lip shape and fullness
  * Skin tone and texture
  * Hair color, style, and texture
  * Unique identifying features (moles, freckles, etc.)
- Do NOT idealize or alter their appearances
- Keep their natural proportions and characteristics
"""
        else:
            people_description = """
CRITICAL INSTRUCTIONS FOR FACIAL ACCURACY:
- One person's image is provided as reference
- You MUST maintain their EXACT facial features, including:
  * Face shape and bone structure
  * Eye shape, color, and spacing
  * Nose shape and size
  * Lip shape and fullness
  * Skin tone and texture
  * Hair color, style, and texture
  * Unique identifying features (moles, freckles, etc.)
- Do NOT idealize or alter their appearance
- Keep their natural proportions and characteristics
"""
        
        requirements = f"""

SCENE DESCRIPTION:
{template_prompt}

TECHNICAL REQUIREMENTS:
- Resolution: Minimum 1024x1024 pixels, prefer 4K quality
- Lighting: Professional photography lighting appropriate for the scene
- Composition: Follow rule of thirds, professional framing
- Depth of Field: Appropriate for the scene with subject focus
- Color Grading: Professional wedding photography style
- Background: Detailed and realistic matching the scene description

QUALITY CHECKLIST:
✓ Facial features match reference images EXACTLY
✓ Natural skin tones preserved
✓ Professional photography quality
✓ Appropriate for wedding/romantic context
✓ Photorealistic, not artistic or stylized
✓ Proper lighting and exposure
✓ Sharp focus on subjects' faces
"""
        
        return base_prompt + people_description + requirements

    async def test_generation(self) -> dict:
        """
        Test the image generation service
        
        Returns:
            dict: Status and model information
        """
        try:
            client = genai.Client(api_key=self.api_key)
            logger.info(f"Gemini client initialized with model: {self.model_name}")
            
            return {
                "status": "success",
                "model": self.model_name,
                "message": "Image generation service is ready"
            }
        except Exception as e:
            logger.error(f"Service test failed: {str(e)}", exc_info=True)
            return {
                "status": "error",
                "message": str(e)
            }