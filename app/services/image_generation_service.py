from google import genai
from google.genai import types
from pathlib import Path
import uuid
from app.config import settings
from app.services.watermark_service import WatermarkService
from PIL import Image
import logging

logger = logging.getLogger(__name__)

class ImageGenerationService:
    def __init__(self):
        """Initialize Gemini client for image generation"""
        self.api_key = settings.GEMINI_API_KEY
        self.model_name = "gemini-2.5-flash-image"  # Updated model name
        logger.info(f"✅ Image Generation Service initialized with model: {self.model_name}")
    
    async def generate_image(
        self, 
        user_image_path: str,
        partner_image_path: str = None,
        prompt: str = "",
        add_watermark: bool = False
    ) -> tuple[str, str]:
        """
        Generate image using Gemini API
        
        Args:
            user_image_path: Path to user's image
            partner_image_path: Path to partner's image (optional)
            prompt: Template prompt for image generation
            add_watermark: Whether to add watermark to generated image
            
        Returns:
            tuple: (generated_image_path, watermarked_image_path or None)
        """
        try:
            logger.info(f"🎨 Starting image generation...")
            logger.info(f"   User image: {user_image_path}")
            logger.info(f"   Partner image: {partner_image_path}")
            logger.info(f"   Add watermark: {add_watermark}")
            
            # Convert to Path objects and verify files exist
            user_path = Path(user_image_path)
            if not user_path.exists():
                raise FileNotFoundError(f"User image not found at: {user_image_path}")
            logger.info(f"   ✓ User image exists: {user_path.stat().st_size} bytes")
            
            partner_path = None
            if partner_image_path:
                partner_path = Path(partner_image_path)
                if not partner_path.exists():
                    raise FileNotFoundError(f"Partner image not found at: {partner_image_path}")
                logger.info(f"   ✓ Partner image exists: {partner_path.stat().st_size} bytes")
            
            # Create comprehensive prompt for image generation
            full_prompt = self._create_generation_prompt(prompt, has_partner=partner_image_path is not None)
            logger.info(f"   Prompt created (length: {len(full_prompt)} chars)")
            
            # Initialize the client with API key
            logger.info(f"   Initializing Gemini client...")
            client = genai.Client(api_key=self.api_key)
            
            # Load images using PIL
            logger.info(f"   Loading images with PIL...")
            user_image = Image.open(user_path)
            logger.info(f"   ✓ User image loaded: {user_image.size}")
            
            # Prepare contents array
            contents = [full_prompt, user_image]
            
            # Add partner image if provided
            if partner_path:
                partner_image = Image.open(partner_path)
                logger.info(f"   ✓ Partner image loaded: {partner_image.size}")
                contents.append(partner_image)
            
            # Define the generation configuration for image output
            config = types.GenerateContentConfig(
                response_modalities=["IMAGE"],  # Crucial: Output image
                image_config=types.ImageConfig(
                    aspect_ratio="1:1"  # Output aspect ratio
                )
            )
            
            logger.info(f"   Sending request to Gemini model: {self.model_name}...")
            
            # Call the API
            response = client.models.generate_content(
                model=self.model_name,
                contents=contents,
                config=config
            )
            
            logger.info("   ✓ Gemini API response received")
            
            # Save generated image
            generated_dir = Path(settings.GENERATED_DIR)
            generated_dir.mkdir(parents=True, exist_ok=True)
            
            generated_filename = f"{uuid.uuid4()}.png"
            generated_path = generated_dir / generated_filename
            
            # Process and save the response
            if response.candidates and response.candidates[0].content.parts:
                part = response.candidates[0].content.parts[0]
                if hasattr(part, 'inline_data') and part.inline_data:
                    # Convert base64 data to PIL Image and save
                    generated_image = part.as_image()
                    generated_image.save(str(generated_path))
                    logger.info(f"   ✅ Image generated and saved: {generated_path}")
                else:
                    logger.error("   ❌ Response did not contain inline image data.")
                    raise Exception("No inline image data found in Gemini response")
            else:
                logger.error("   ❌ No valid candidates or parts found in the response.")
                raise Exception("No valid response from Gemini API")
            
            # Add watermark if needed
            watermarked_path = None
            if add_watermark:
                watermarked_filename = f"{uuid.uuid4()}_watermarked.png"
                watermarked_path = str(generated_dir / watermarked_filename)
                WatermarkService.add_watermark(
                    str(generated_path),
                    watermarked_path,
                    settings.WATERMARK_TEXT
                )
                logger.info(f"   ✅ Watermark added: {watermarked_path}")
            
            logger.info(f"🎉 Image generation completed successfully!")
            return str(generated_path), watermarked_path
            
        except FileNotFoundError as e:
            logger.error(f"❌ File not found: {str(e)}")
            raise Exception(f"File not found: {str(e)}")
        except Exception as e:
            logger.error(f"❌ Image generation failed: {str(e)}")
            logger.exception("Full traceback:")
            raise Exception(f"Image generation failed: {str(e)}")
    
    def _create_generation_prompt(self, template_prompt: str, has_partner: bool = False) -> str:
        """Enhanced version with better accuracy"""
        
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
        Test the image generation service with Gemini API
        Returns status and model info
        """
        try:
            client = genai.Client(api_key=self.api_key)
            logger.info(f"✅ Gemini client initialized with model: {self.model_name}")
            
            return {
                "status": "success",
                "model": self.model_name,
                "message": "Image generation service is ready"
            }
        except Exception as e:
            logger.error(f"❌ Test failed: {str(e)}")
            return {
                "status": "error",
                "message": str(e)
            }