import logging
from google import genai
from google.genai import types
from pathlib import Path
import uuid
from app.config import settings
from app.services.watermark_service import WatermarkService
from app.services.storage_service import StorageService
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
    
    def _optimize_image(self, image_path: str) -> Image.Image:
        """
        Optimize image for Gemini API - supports both local paths and S3 URLs
        """
        # Handle S3 URLs
        if image_path.startswith('http'):
            import requests
            response = requests.get(image_path)
            img = Image.open(io.BytesIO(response.content))
            original_size = len(response.content) / (1024 * 1024)
        else:
            # Local file
            path = Path(image_path)
            img = Image.open(path)
            original_size = path.stat().st_size / (1024 * 1024)
        
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
        Generate image using Gemini API with S3 support
        Returns S3 URLs or local paths based on USE_S3 setting
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
            
            # Save generated image (locally first, then upload to S3 if enabled)
            generated_path = self._save_generated_image(response)
            
            # Upload to S3 if enabled
            if settings.USE_S3:
                generated_path = StorageService.save_generated_image(
                    generated_path, 
                    folder="generated"
                )
            
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
            self._validate_file_exists(path, f"User {i}")
            pil_img = self._optimize_image(path)
            user_pil_images.append(pil_img)
            logger.debug(f"✓ User image {i} optimized to 9:16: {pil_img.size}")
        
        # Load and optimize partner images (ALL converted to 9:16)
        partner_pil_images = []
        for i, path in enumerate(partner_images, 1):
            self._validate_file_exists(path, f"Partner {i}")
            pil_img = self._optimize_image(path)
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
        
        self._validate_file_exists(couple_image_path, "Couple")
        couple_image = self._optimize_image(couple_image_path)
        logger.debug(f"✓ Couple image optimized to 9:16: {couple_image.size}")
        
        full_prompt = self._create_couple_prompt(prompt)
        contents = [full_prompt, couple_image]
        
        return contents, full_prompt
    
    def _validate_file_exists(self, file_path: str, label: str):
        """Validate file exists (supports both local and S3)"""
        if file_path.startswith('http'):
            # S3 URL - we'll validate on download
            logger.debug(f"{label} image is S3 URL: {file_path}")
            return
        
        # Local path
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"{label} image not found at: {file_path}")
    
    def _save_generated_image(self, response) -> str:
        """Save generated image locally (will be uploaded to S3 later if enabled)"""
        if not response.candidates or not response.candidates[0].content.parts:
            raise Exception("No valid response from Gemini API")
        
        part = response.candidates[0].content.parts[0]
        if not hasattr(part, 'inline_data') or not part.inline_data:
            raise Exception("No inline image data found in response")
        
        # Create output directory (always save locally first)
        generated_dir = Path(settings.GENERATED_DIR)
        generated_dir.mkdir(parents=True, exist_ok=True)
        
        # Save image
        generated_filename = f"{uuid.uuid4()}.png"
        generated_path = generated_dir / generated_filename
        
        generated_image = part.as_image()
        generated_image.save(str(generated_path))
        
        # Log final dimensions
        logger.info(f"💾 Image saved locally: {generated_path} ({generated_image.size})")
        return str(generated_path)
        
    def _add_watermark(self, image_path: str) -> str:
        """Add watermark to generated image"""
        try:
            # Download from S3 if needed
            if image_path.startswith('http'):
                import requests
                import tempfile
                
                response = requests.get(image_path)
                with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as tmp:
                    tmp.write(response.content)
                    local_temp = tmp.name
            else:
                local_temp = image_path
            
            # Create watermarked version locally
            generated_dir = Path(settings.GENERATED_DIR)
            generated_dir.mkdir(parents=True, exist_ok=True)
            watermarked_filename = f"{uuid.uuid4()}_watermarked.png"
            watermarked_local_path = str(generated_dir / watermarked_filename)
            
            WatermarkService.add_watermark(
                local_temp,
                watermarked_local_path,
                settings.WATERMARK_TEXT
            )
            
            # Upload to S3 if enabled
            if settings.USE_S3:
                watermarked_path = StorageService.save_generated_image(
                    watermarked_local_path,
                    folder="generated"
                )
            else:
                watermarked_path = watermarked_local_path
            
            logger.info(f"🖼️ Watermark added: {watermarked_path}")
            return watermarked_path
            
        except Exception as e:
            logger.error(f"❌ Watermark addition failed: {str(e)}")
            return image_path
    
    def _create_flexible_prompt(self, template_prompt: str, user_count: int, partner_count: int) -> str:
        """ULTRA-ENHANCED for pixel-perfect face matching"""
        
        # Build reference description
        if user_count == 1 and partner_count == 1:
            ref_text = "First image = Person A, Second image = Person B"
        else:
            ref_text = f"Images 1-{user_count} = Person A, Images {user_count+1}-{user_count+partner_count} = Person B"
        
        return f"""REFERENCE IMAGES: {ref_text}

PRIMARY OBJECTIVE: Use these reference images as ABSOLUTE templates. The faces in the output MUST be indistinguishable from the reference faces. Imagine you are doing a face transplant - copy EVERY detail pixel by pixel.

CRITICAL FACE MATCHING PROTOCOL (Follow EXACTLY):

PERSON A FACE ANALYSIS:
- Study reference images carefully - memorize their UNIQUE face
- Identify distinguishing features: specific eye shape, nose bridge angle, lip curvature, jaw angle
- Note their natural asymmetries and imperfections
- Lock these features in memory before generating

PERSON B FACE ANALYSIS:
- Study reference images carefully - memorize their UNIQUE face  
- Identify distinguishing features specific to them
- Note their natural asymmetries and imperfections
- Lock these features in memory before generating

FACE REPLICATION CHECKLIST (For BOTH people):
✓ EYES: Copy exact iris color, pupil size, eyelid fold type (monolid/double/hooded), eye corner shape, eyebrow arch pattern, eyebrow thickness, distance between eyes, eye size relative to face
✓ NOSE: Match nose bridge height/width, nostril width and flare, nose tip shape (pointed/round/bulbous), columella visibility, nose length from bridge to tip, side profile angle
✓ MOUTH: Replicate upper lip shape (cupid's bow definition), lower lip fullness, lip color, mouth width relative to nose width, corner of mouth position, philtrum depth
✓ JAW & CHIN: Copy jawline angle (sharp/soft/rounded), chin shape (pointed/square/dimpled), chin projection, jaw width at cheekbones
✓ FACE SHAPE: Replicate overall shape (oval/round/square/heart/diamond), forehead height and width, cheekbone prominence, face width-to-length ratio
✓ SKIN: Match exact complexion (fair/wheatish/dusky), undertone (warm/cool/olive), natural texture with pores, any moles/freckles/beauty marks in exact locations, natural shadowing under cheekbones
✓ HAIR: Copy hair color exactly (including highlights/lowlights), texture pattern (straight/wavy/curly/coily), hairline shape, widow's peak if present, hair volume and density
✓ EARS: If visible, match ear size, shape, and position relative to eyes
✓ AGE FEATURES: Preserve crow's feet, smile lines, under-eye appearance, forehead lines, skin elasticity - these make faces RECOGNIZABLE

BODY MATCHING PROTOCOL:
✓ HEIGHT RATIO: If both visible in references, maintain exact height difference
✓ BODY BUILD: Match body frame - ectomorph/mesomorph/endomorph for each person
✓ SHOULDER WIDTH: Proportional to their head size in references
✓ SKIN TONE: Body must match face skin tone exactly - no disconnect
✓ HANDS: Study reference hand proportions, finger length, skin texture - then replicate with EXACTLY 5 fingers per hand, natural positioning
✓ POSTURE: Match their natural body language from references

SCENE INTEGRATION: {template_prompt}

COMPOSITION REQUIREMENTS:
- Vertical 9:16 phone portrait format
- Full body or 3/4 length showing both people clearly
- Faces are PRIMARY FOCUS - must be pin-sharp and detailed
- Background supports but doesn't distract from faces
- Natural couple chemistry and body language

TECHNICAL SPECIFICATIONS:
- Hyper-photorealistic - looks like actual photograph, NOT AI art
- Shot on professional camera (Canon EOS R5 / Sony A7IV equivalent)
- Lens: 35mm-85mm focal length equivalent 
- Sharp focus on faces with visible skin pores and texture
- Shallow depth of field on background (f/1.8 - f/2.8)
- Natural lighting matching scene time/place
- Professional color grading - warm romantic tones but realistic
- Resolution: High detail equivalent to 8K capture

ABSOLUTE PROHIBITIONS:
❌ DO NOT beautify or "improve" faces - use them EXACTLY as provided
❌ DO NOT smooth skin or apply digital makeup
❌ DO NOT make faces more symmetrical than they naturally are
❌ DO NOT use generic "attractive" AI faces - faces must be UNIQUE to references
❌ DO NOT westernize ethnic features or lighten skin tones
❌ DO NOT create model-perfect faces - keep natural human imperfections
❌ DO NOT blur faces - they must be crystal clear
❌ DO NOT create extra/missing fingers (EXACTLY 5 per hand)
❌ DO NOT create twisted, deformed, or anatomically incorrect hands
❌ DO NOT cross or misalign eyes
❌ DO NOT change face proportions or body types from references
❌ DO NOT add jewelry/accessories not mentioned in scene description

VALIDATION CHECK:
Before finalizing output, verify: "If shown the reference and output side-by-side, would someone immediately recognize these as the same people?" If NO, regenerate with more accurate faces.

OUTPUT: A professional pre-wedding photograph in vertical phone format with EXACT FACE MATCHES from reference images naturally integrated into the described scene."""
            
    def _create_couple_prompt(self, template_prompt: str) -> str:
        """ULTRA-ENHANCED for pixel-perfect couple face matching"""
        return f"""REFERENCE IMAGE: One image showing both people together.

PRIMARY OBJECTIVE: Use this reference as an ABSOLUTE template. The faces and body proportions in the output MUST be indistinguishable from the reference. Imagine you are doing face transplants for both people - copy EVERY detail pixel by pixel.

CRITICAL DUAL-FACE MATCHING PROTOCOL:

ANALYZE BOTH PEOPLE IN REFERENCE:
- Study how they look TOGETHER - their relative sizes, heights, proportions
- Memorize Person 1's UNIQUE face - all distinguishing features
- Memorize Person 2's UNIQUE face - all distinguishing features  
- Note their natural chemistry and body language
- Observe their exact height difference and body size ratio

PERSON 1 FACE REPLICATION CHECKLIST:
✓ EYES: Copy exact iris color, eyelid type, eye shape, eyebrow pattern, eye spacing
✓ NOSE: Match bridge height/width, nostril shape, tip shape, nose length, side angle
✓ MOUTH: Replicate lip shapes, fullness, cupid's bow, mouth width, corner position
✓ JAW/CHIN: Copy jawline angle, chin shape and projection, jaw width
✓ FACE SHAPE: Replicate overall face geometry and proportions
✓ SKIN: Match complexion, undertone, texture, moles/marks in exact locations
✓ HAIR: Copy color, texture, hairline, volume exactly
✓ AGE FEATURES: Preserve wrinkles, lines, natural aging signs

PERSON 2 FACE REPLICATION CHECKLIST:
✓ EYES: Copy exact iris color, eyelid type, eye shape, eyebrow pattern, eye spacing
✓ NOSE: Match bridge height/width, nostril shape, tip shape, nose length, side angle
✓ MOUTH: Replicate lip shapes, fullness, cupid's bow, mouth width, corner position
✓ JAW/CHIN: Copy jawline angle, chin shape and projection, jaw width
✓ FACE SHAPE: Replicate overall face geometry and proportions
✓ SKIN: Match complexion, undertone, texture, moles/marks in exact locations
✓ HAIR: Copy color, texture, hairline, volume exactly
✓ AGE FEATURES: Preserve wrinkles, lines, natural aging signs

RELATIONSHIP & PROPORTION MATCHING:
✓ HEIGHT DIFFERENCE: Preserve EXACT height difference from reference
✓ SIZE RATIO: Who is broader/taller/bigger - maintain this relationship precisely
✓ BODY BUILD: Match each person's build type - slim/athletic/average/heavy
✓ SHOULDER WIDTH: Proportional to each person's head as in reference
✓ BODY LANGUAGE: Replicate their natural chemistry - how they stand/sit together
✓ PHYSICAL COMFORT: Match how close/distant they naturally appear
✓ SKIN TONE: Body matches face for BOTH people
✓ HANDS: Study reference hand size/shape, replicate with EXACTLY 5 fingers each

SCENE INTEGRATION: {template_prompt}

COMPOSITION REQUIREMENTS:
- Vertical 9:16 phone portrait format
- Full body or 3/4 length showing both people clearly
- BOTH faces are PRIMARY FOCUS - pin-sharp and detailed
- Maintain their relative positioning and chemistry from reference
- Background enhances but doesn't distract from the couple

TECHNICAL SPECIFICATIONS:
- Hyper-photorealistic - actual photograph quality, NOT AI art
- Professional camera quality (Canon EOS R5 / Sony A7IV)
- Lens: 35mm-85mm focal length equivalent
- Sharp focus on BOTH faces with visible skin texture
- Shallow depth of field on background (f/1.8 - f/2.8)
- Natural lighting appropriate to scene
- Professional color grading - warm romantic but realistic
- High resolution equivalent to 8K capture

ABSOLUTE PROHIBITIONS:
❌ DO NOT beautify either face - copy them EXACTLY as provided
❌ DO NOT smooth skin or apply digital makeup to either person
❌ DO NOT make faces more symmetrical than natural
❌ DO NOT use generic "attractive" faces - both must be UNIQUE to reference
❌ DO NOT westernize features or lighten skin tones
❌ DO NOT change the height difference or size relationship
❌ DO NOT create model-perfect faces - keep natural imperfections
❌ DO NOT blur either face - both must be crystal clear
❌ DO NOT create extra/missing fingers (EXACTLY 5 per hand, both people)
❌ DO NOT create deformed hands or unnatural hand positions
❌ DO NOT cross or misalign eyes on either person
❌ DO NOT change body proportions from reference
❌ DO NOT alter their natural relationship dynamic

VALIDATION CHECK:
Before finalizing: "If shown the reference and output side-by-side, would someone immediately recognize both people as identical?" If NO, regenerate with more accurate face matches.

OUTPUT: A professional pre-wedding photograph in vertical phone format with EXACT FACE AND BODY MATCHES for both people from the reference image naturally integrated into the described scene."""