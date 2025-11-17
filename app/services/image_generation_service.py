import google.generativeai as genai
from pathlib import Path
import uuid
from app.config import settings
from app.services.watermark_service import WatermarkService
from PIL import Image
import base64
import io
import logging

logger = logging.getLogger(__name__)

class ImageGenerationService:
    def __init__(self):
        """Initialize Gemini client for image generation"""
        genai.configure(api_key=settings.GEMINI_API_KEY)
        # Use Gemini 2.5 Flash for image generation (or 2.0 for testing)
        self.model_name = "gemini-2.0-flash-exp"  # Change to gemini-2.5-flash-image when available
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
            
            # Load and prepare images
            user_image = Image.open(user_image_path)
            logger.info(f"   User image loaded: {user_image.size}")
            
            # Prepare images for Gemini
            images_for_prompt = [user_image]
            
            if partner_image_path:
                partner_image = Image.open(partner_image_path)
                images_for_prompt.append(partner_image)
                logger.info(f"   Partner image loaded: {partner_image.size}")
            
            # Create comprehensive prompt for image generation
            full_prompt = self._create_generation_prompt(prompt, has_partner=partner_image_path is not None)
            logger.info(f"   Prompt created (length: {len(full_prompt)} chars)")
            
            # Generate image using Gemini
            logger.info(f"   Calling Gemini API with model: {self.model_name}")
            model = genai.GenerativeModel(self.model_name)
            
            # Upload images to Gemini
            uploaded_images = []
            for img in images_for_prompt:
                # Convert PIL Image to bytes
                img_byte_arr = io.BytesIO()
                img.save(img_byte_arr, format='PNG')
                img_byte_arr.seek(0)
                
                # Upload to Gemini
                uploaded_file = genai.upload_file(img_byte_arr, mime_type="image/png")
                uploaded_images.append(uploaded_file)
            
            logger.info(f"   Uploaded {len(uploaded_images)} images to Gemini")
            
            # Generate content
            response = model.generate_content([
                full_prompt,
                *uploaded_images
            ])
            
            logger.info("   Gemini API response received")
            
            # Save generated image
            generated_dir = Path(settings.GENERATED_DIR)
            generated_dir.mkdir(parents=True, exist_ok=True)
            
            generated_filename = f"{uuid.uuid4()}.png"
            generated_path = generated_dir / generated_filename
            
            # Process Gemini response
            # Note: Gemini 2.0/2.5 with image generation capability should return image data
            # If using Imagen or another model, adjust accordingly
            
            if hasattr(response, 'candidates') and response.candidates:
                candidate = response.candidates[0]
                if hasattr(candidate, 'content') and hasattr(candidate.content, 'parts'):
                    for part in candidate.content.parts:
                        if hasattr(part, 'inline_data'):
                            # Image data found
                            image_data = base64.b64decode(part.inline_data.data)
                            generated_image = Image.open(io.BytesIO(image_data))
                            generated_image.save(str(generated_path))
                            logger.info(f"   ✅ Image generated and saved: {generated_path}")
                            break
                    else:
                        raise Exception("No image data found in Gemini response")
                else:
                    raise Exception("Unexpected response structure from Gemini")
            else:
                raise Exception("No valid response from Gemini")
            
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
            
        except Exception as e:
            logger.error(f"❌ Image generation failed: {str(e)}")
            raise Exception(f"Image generation failed: {str(e)}")
    
    def _create_generation_prompt(self, template_prompt: str, has_partner: bool = False) -> str:
        """Create a comprehensive prompt for image generation"""
        
        base_prompt = """You are a professional wedding photographer and AI image generator.
Your task is to create a stunning, high-quality pre-wedding photoshoot image."""
        
        if has_partner:
            people_description = """
I am providing you with two images - one of a person and one of their partner.
Please use both people in the generated image, maintaining their facial features, skin tones, and unique characteristics accurately."""
        else:
            people_description = """
I am providing you with an image of a person.
Please use this person in the generated image, maintaining their facial features, skin tone, and unique characteristics accurately."""
        
        requirements = f"""

Scene Requirements:
{template_prompt}

Quality Standards:
- Create a photorealistic, high-resolution image (at least 1024x1024 pixels)
- Ensure natural lighting that flatters the subject(s)
- Maintain accurate facial features and skin tones from the provided images
- Create professional composition with proper depth of field
- Ensure the scene matches the template description perfectly
- Add appropriate props, background elements, and atmospheric effects
- Make the image look like it was taken by a professional photographer

Style Guidelines:
- The image should look natural and authentic, not overly edited
- Colors should be vibrant but realistic
- The mood should be romantic and joyful
- Ensure the subjects look comfortable and naturally posed
"""
        
        return base_prompt + people_description + requirements
    
    async def test_generation(self) -> dict:
        """
        Test the image generation service with Gemini API
        Returns status and model info
        """
        try:
            model = genai.GenerativeModel(self.model_name)
            logger.info(f"✅ Gemini model loaded: {self.model_name}")
            
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