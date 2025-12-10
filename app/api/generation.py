import logging
from google import genai
from google.genai import types
from pathlib import Path
import uuid
from app.config import settings
from app.services.watermark_service import WatermarkService
from PIL import Image
from typing import Optional, List, Tuple
from app.models.generation import GenerationMode
import io

logger = logging.getLogger(__name__)

class ImageGenerationService:
    # Gemini API limits
    MAX_IMAGE_SIZE_MB = 4  # Max 4MB per image
    MAX_DIMENSION = 3072  # Max 3072px on any side
    RECOMMENDED_DIMENSION = 1024  # Recommended for best results
    
    # Target aspect ratio for phone
    TARGET_ASPECT_WIDTH = 9
    TARGET_ASPECT_HEIGHT = 16
    
    def __init__(self):
        """Initialize Gemini client for image generation"""
        if not settings.GEMINI_API_KEY:
            logger.error("GEMINI_API_KEY not configured")
            raise ValueError("GEMINI_API_KEY is required")
            
        self.api_key = settings.GEMINI_API_KEY
        self.model_name = "gemini-2.5-flash-image"
        logger.info(f"Image Generation Service initialized with model: {self.model_name}")
    
    def _optimize_image(self, image_path: Path) -> Image.Image:
        """
        Optimize image for Gemini API:
        - Convert to 9:16 ratio to force output ratio
        - Resize if too large
        - Compress if file size too big
        """
        img = Image.open(image_path)
        original_size = image_path.stat().st_size / (1024 * 1024)  # MB
        
        logger.debug(f"Original image: {img.size}, {original_size:.2f}MB")
        
        # CRITICAL FIX: Convert to 9:16 ratio to force output ratio
        target_ratio = self.TARGET_ASPECT_WIDTH / self.TARGET_ASPECT_HEIGHT
        current_ratio = img.width / img.height
        
        if abs(current_ratio - target_ratio) > 0.01:
            # Calculate new dimensions maintaining 9:16 ratio
            if current_ratio > target_ratio:
                # Image is too wide, crop width
                new_width = int(img.height * target_ratio)
                left = (img.width - new_width) // 2
                img = img.crop((left, 0, left + new_width, img.height))
            else:
                # Image is too tall, crop height
                new_height = int(img.width / target_ratio)
                top = (img.height - new_height) // 2
                img = img.crop((0, top, img.width, top + new_height))
            
            logger.debug(f"Cropped to 9:16 ratio: {img.size}")
        
        # Resize if dimensions too large (maintain 9:16)
        if max(img.size) > self.RECOMMENDED_DIMENSION:
            # Scale down maintaining 9:16 ratio
            if img.width > img.height:
                new_height = self.RECOMMENDED_DIMENSION
                new_width = int(new_height * target_ratio)
            else:
                new_height = self.RECOMMENDED_DIMENSION
                new_width = int(new_height * target_ratio)
            
            img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
            logger.debug(f"Resized to: {img.size}")
        
        # Compress if file size too large
        if original_size > self.MAX_IMAGE_SIZE_MB:
            buffer = io.BytesIO()
            quality = 85
            
            while quality > 20:
                buffer.seek(0)
                buffer.truncate()
                img.save(buffer, format='JPEG', quality=quality, optimize=True)
                size_mb = buffer.tell() / (1024 * 1024)
                
                if size_mb <= self.MAX_IMAGE_SIZE_MB:
                    break
                quality -= 10
            
            buffer.seek(0)
            img = Image.open(buffer)
            logger.debug(f"Compressed to: {size_mb:.2f}MB at quality {quality}")
        
        # Convert RGBA to RGB if needed
        if img.mode == 'RGBA':
            background = Image.new('RGB', img.size, (255, 255, 255))
            background.paste(img, mask=img.split()[3])
            img = background
            logger.debug("Converted RGBA to RGB")
        
        return img
    
    async def generate_image(
        self, 
        generation_mode: GenerationMode,
        user_images: Optional[List[str]] = None,
        partner_images: Optional[List[str]] = None,
        couple_image_path: Optional[str] = None,
        prompt: str = "",
        add_watermark: bool = False
    ) -> Tuple[str, Optional[str]]:
        """
        Generate image using Gemini API with robust error handling
        """
        try:
            logger.info(f"🚀 Starting image generation - Mode: {generation_mode}")
            
            # Prepare content based on mode
            if generation_mode == GenerationMode.FLEXIBLE:
                contents, full_prompt = self._prepare_flexible_mode(
                    user_images, partner_images, prompt
                )
            elif generation_mode == GenerationMode.COUPLE:
                contents, full_prompt = self._prepare_couple_mode(
                    couple_image_path, prompt
                )
            else:
                raise ValueError(f"Invalid generation mode: {generation_mode}")
            
            # Log prompt length
            prompt_length = len(full_prompt)
            logger.info(f"📝 Prompt length: {prompt_length} characters")
            
            # Initialize Gemini client
            client = genai.Client(api_key=self.api_key)
            
            # Configure generation - PHONE RATIO (9:16)
            config = types.GenerateContentConfig(
                response_modalities=["IMAGE"],
                image_config=types.ImageConfig(aspect_ratio="9:16")
            )
            
            logger.info(f"📤 Sending request to Gemini API with 9:16 ratio...")
            
            # Generate image with retry logic
            max_retries = 2
            for attempt in range(max_retries):
                try:
                    response = client.models.generate_content(
                        model=self.model_name,
                        contents=contents,
                        config=config
                    )
                    logger.info("📥 Gemini API response received")
                    break
                    
                except Exception as api_error:
                    error_msg = str(api_error)
                    
                    # Handle specific errors
                    if "500" in error_msg or "INTERNAL" in error_msg:
                        if attempt < max_retries - 1:
                            logger.warning(f"⚠️ Gemini 500 error (attempt {attempt+1}/{max_retries}), retrying...")
                            continue
                        else:
                            raise Exception(
                                "Gemini API is experiencing issues. This is typically due to: "
                                "(1) Image complexity, (2) API overload, or (3) Prompt length. "
                                "Please try again with fewer/smaller images or a simpler prompt."
                            )
                    
                    elif "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg:
                        raise Exception(
                            "Rate limit exceeded. Please wait a moment before trying again."
                        )
                    
                    elif "400" in error_msg or "INVALID_ARGUMENT" in error_msg:
                        raise Exception(
                            "Invalid request. Check that all images are valid and under 4MB."
                        )
                    
                    else:
                        raise Exception(f"Gemini API error: {error_msg}")
            
            # Save generated image
            generated_path = self._save_generated_image(response)
            
            # Add watermark if requested
            watermarked_path = None
            if add_watermark:
                watermarked_path = self._add_watermark(generated_path)
            
            logger.info("✅ Image generation completed successfully")
            return str(generated_path), watermarked_path
            
        except Exception as e:
            logger.error(f"❌ Image generation failed: {str(e)}", exc_info=True)
            raise Exception(f"Image generation failed: {str(e)}")
    
    def _prepare_flexible_mode(
        self, 
        user_images: List[str], 
        partner_images: List[str],
        prompt: str
    ) -> Tuple[list, str]:
        """Prepare content for FLEXIBLE mode with optimization"""
        logger.info(f"Preparing FLEXIBLE mode: {len(user_images)} user + {len(partner_images)} partner images")
        
        # Load and optimize user images (ALL converted to 9:16)
        user_pil_images = []
        for i, path in enumerate(user_images, 1):
            img_path = self._validate_and_get_path(path, f"User {i}")
            pil_img = self._optimize_image(img_path)
            user_pil_images.append(pil_img)
            logger.debug(f"✓ User image {i} optimized to 9:16: {pil_img.size}")
        
        # Load and optimize partner images (ALL converted to 9:16)
        partner_pil_images = []
        for i, path in enumerate(partner_images, 1):
            img_path = self._validate_and_get_path(path, f"Partner {i}")
            pil_img = self._optimize_image(img_path)
            partner_pil_images.append(pil_img)
            logger.debug(f"✓ Partner image {i} optimized to 9:16: {pil_img.size}")
        
        # Create optimized prompt
        full_prompt = self._create_flexible_prompt(
            prompt, 
            len(user_images), 
            len(partner_images)
        )
        
        # Build contents
        contents = [full_prompt] + user_pil_images + partner_pil_images
        
        return contents, full_prompt
    
    def _prepare_couple_mode(
        self,
        couple_image_path: str,
        prompt: str
    ) -> Tuple[list, str]:
        """Prepare content for COUPLE mode with optimization"""
        logger.info("Preparing COUPLE mode generation")
        
        couple_path = self._validate_and_get_path(couple_image_path, "Couple")
        couple_image = self._optimize_image(couple_path)
        logger.debug(f"✓ Couple image optimized to 9:16: {couple_image.size}")
        
        full_prompt = self._create_couple_prompt(prompt)
        contents = [full_prompt, couple_image]
        
        return contents, full_prompt
    
    def _validate_and_get_path(self, file_path: str, label: str) -> Path:
        """Validate file exists and return Path object"""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"{label} image not found at: {file_path}")
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
        
        # Log final dimensions
        logger.info(f"💾 Image saved: {generated_path} ({generated_image.size})")
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
            
            logger.info(f"🖼️ Watermark added: {watermarked_path}")
            return watermarked_path
            
        except Exception as e:
            logger.error(f"❌ Watermark addition failed: {str(e)}")
            return str(image_path)
    
    def _create_flexible_prompt(
        self, 
        template_prompt: str, 
        user_count: int,
        partner_count: int
    ) -> str:
        """
        ENHANCED for maximum face and body accuracy
        """
        
        # Build reference description
        if user_count == 1 and partner_count == 1:
            ref_text = "First image = Person A, Second image = Person B"
        else:
            ref_text = f"Images 1-{user_count} = Person A, Images {user_count+1}-{user_count+partner_count} = Person B"
        
        return f"""REFERENCE IMAGES: {ref_text}

TASK: Create a photorealistic pre-wedding portrait using the EXACT people from reference images.

CRITICAL FACE ACCURACY RULES:
1. FACIAL STRUCTURE: Copy exact bone structure, face shape (round/oval/square), jawline definition, chin shape, forehead width and height
2. EYES: Match exact eye shape, size, spacing between eyes, eyelid shape, eyebrow thickness and arch, eye color depth
3. NOSE: Preserve exact nose bridge width, nostril shape and size, nose tip shape, nose length and projection
4. MOUTH: Copy exact lip thickness (upper and lower), lip width, mouth corner shape, teeth visibility when smiling
5. SKIN: Maintain exact skin tone, undertones (warm/cool), natural texture, pores, any moles, freckles, or birthmarks, natural shadows and contours
6. HAIR: Match exact hair color, texture (straight/wavy/curly), hairline shape, volume, styling direction
7. ETHNICITY: Preserve all ethnic facial characteristics - NO westernization or generic features
8. ASYMMETRY: Keep natural facial asymmetries - faces are NOT perfectly symmetrical
9. AGE MARKERS: Maintain natural age-appropriate features - laugh lines, under-eye area, skin elasticity

BODY ACCURACY RULES:
1. BODY PROPORTIONS: Match exact height difference between Person A and Person B (if visible in references)
2. BUILD: Preserve body type - slim/athletic/average/heavy build for each person
3. SHOULDERS: Match shoulder width relative to head size
4. POSTURE: Natural, relaxed posture - no stiff or unnatural poses
5. HANDS: Anatomically correct hands with EXACTLY 5 fingers per hand, natural hand size proportional to body, realistic knuckles and skin texture
6. SKIN TONE CONSISTENCY: Body skin tone must match face skin tone exactly

SCENE DESCRIPTION: {template_prompt}

COMPOSITION & FORMAT:
- Vertical phone format (9:16 aspect ratio)
- Full body or 3/4 length composition showing both people
- Professional pre-wedding photography composition
- Both faces clearly visible and in sharp focus
- Natural, romantic interaction between the couple

TECHNICAL REQUIREMENTS:
- Ultra-photorealistic rendering, NOT artistic or stylized
- Professional DSLR photography quality
- Natural lighting with soft shadows
- Sharp focus on faces, slight depth of field on background
- High detail on faces (8K quality), skin pores visible
- Natural color grading - warm, romantic but realistic tones

ABSOLUTE PROHIBITIONS:
- DO NOT apply beauty filters, face smoothing, or skin retouching
- DO NOT change any facial features from references
- DO NOT create generic "AI pretty faces"
- DO NOT add makeup unless visible in reference images
- DO NOT create extra fingers (must be EXACTLY 5 per hand)
- DO NOT create deformed, twisted, or unnatural hands
- DO NOT blur faces or create out-of-focus faces
- DO NOT cross eyes or create misaligned eyes
- DO NOT change body proportions or height differences
- DO NOT create cartoonish or anime-style features

FINAL OUTPUT: A professional, photorealistic pre-wedding portrait in vertical phone format with the EXACT faces and bodies from reference images placed naturally in the described scene."""
            
    def _create_couple_prompt(self, template_prompt: str) -> str:
        """
        ENHANCED for couple mode - maximum face and body accuracy
        """
        return f"""REFERENCE IMAGE: One image showing both people together.

TASK: Create a photorealistic pre-wedding portrait preserving the EXACT appearance and relationship of both people.

CRITICAL FACE ACCURACY RULES:
1. FACIAL STRUCTURE: Copy exact bone structure, face shape, jawline, chin shape, forehead for BOTH people
2. EYES: Match exact eye shape, size, spacing, eyelid shape, eyebrow style, eye color for each person
3. NOSE: Preserve exact nose bridge, nostril shape, nose tip, length for each person
4. MOUTH: Copy exact lip thickness, width, mouth shape, smile characteristics for each person
5. SKIN: Maintain exact skin tone, texture, any moles, freckles, natural contours for both people
6. HAIR: Match exact hair color, texture, hairline, volume, styling for each person
7. ETHNICITY: Preserve all ethnic characteristics for both people - NO generic features
8. ASYMMETRY: Keep natural facial asymmetries for both faces
9. AGE MARKERS: Maintain age-appropriate features for both people

RELATIONSHIP & BODY ACCURACY:
1. HEIGHT DIFFERENCE: Preserve exact height difference between the two people as shown in reference
2. BODY BUILD: Match body type and build for each person (slim/athletic/average/heavy)
3. PROPORTIONS: Keep body proportions (shoulder width, torso length) for each person
4. RELATIVE SIZE: Maintain correct relative sizing - who is taller, broader, etc.
5. HANDS: Anatomically correct hands with EXACTLY 5 fingers per hand for both people
6. SKIN TONE: Body skin tone must match face skin tone for each person
7. POSTURE: Natural, comfortable poses showing their real relationship dynamic

SCENE DESCRIPTION: {template_prompt}

COMPOSITION & FORMAT:
- Vertical phone format (9:16 aspect ratio)
- Full body or 3/4 length showing both people clearly
- Professional pre-wedding photography composition
- Both faces clearly visible and in sharp focus
- Maintain their natural chemistry and body language from reference

TECHNICAL REQUIREMENTS:
- Ultra-photorealistic rendering, NOT artistic interpretation
- Professional DSLR photography quality
- Natural, romantic lighting with soft shadows
- Sharp focus on both faces with visible skin detail
- High resolution (8K quality) with natural pores and texture
- Warm, romantic color grading but realistic tones

ABSOLUTE PROHIBITIONS:
- DO NOT apply beauty filters or face smoothing to either person
- DO NOT change facial features of either person
- DO NOT make faces more "attractive" or generic
- DO NOT alter height difference or body proportions
- DO NOT create extra fingers (must be EXACTLY 5 per hand for both)
- DO NOT create deformed, twisted, or unnatural hands
- DO NOT blur either face or create soft focus on faces
- DO NOT cross eyes or misalign eyes on either person
- DO NOT change the relationship dynamic or chemistry
- DO NOT add makeup unless visible in reference

FINAL OUTPUT: A professional, photorealistic pre-wedding portrait in vertical phone format with the EXACT appearance, proportions, and relationship of both people from the reference image placed naturally in the described scene."""