import logging
from google import genai
from google.genai import types
from pathlib import Path
import uuid
from app.config import settings
from app.services.watermark_service import WatermarkService
from PIL import Image
from typing import Optional, Tuple, Dict
from app.models.generation import GenerationMode

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
        generation_mode: GenerationMode,
        user_image_path: Optional[str] = None,
        partner_image_path: Optional[str] = None,
        couple_image_path: Optional[str] = None,
        user_images: Optional[Dict[str, str]] = None,
        partner_images: Optional[Dict[str, str]] = None,
        prompt: str = "",
        add_watermark: bool = False
    ) -> Tuple[str, Optional[str]]:
        """
        Generate image using Gemini API with support for multiple modes
        
        Args:
            generation_mode: Mode of generation (SINGLE, COUPLE, MULTI_ANGLE)
            user_image_path: Path to user's image (Mode 1)
            partner_image_path: Path to partner's image (Mode 1)
            couple_image_path: Path to couple image (Mode 2)
            user_images: Dict of user images {angle: path} (Mode 3)
            partner_images: Dict of partner images {angle: path} (Mode 3)
            prompt: Template prompt for image generation
            add_watermark: Whether to add watermark to generated image
            
        Returns:
            Tuple[str, Optional[str]]: (generated_image_path, watermarked_image_path)
            
        Raises:
            Exception: If image generation fails
        """
        try:
            logger.info(f"Starting image generation - Mode: {generation_mode}")
            
            # Load images based on mode
            if generation_mode == GenerationMode.SINGLE:
                contents, full_prompt = self._prepare_single_mode(
                    user_image_path, partner_image_path, prompt
                )
            elif generation_mode == GenerationMode.COUPLE:
                contents, full_prompt = self._prepare_couple_mode(
                    couple_image_path, prompt
                )
            elif generation_mode == GenerationMode.MULTI_ANGLE:
                contents, full_prompt = self._prepare_multi_angle_mode(
                    user_images, partner_images, prompt
                )
            else:
                raise ValueError(f"Invalid generation mode: {generation_mode}")
            
            # Initialize Gemini client
            client = genai.Client(api_key=self.api_key)
            
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
    
    def _prepare_single_mode(
        self, 
        user_image_path: str, 
        partner_image_path: Optional[str],
        prompt: str
    ) -> Tuple[list, str]:
        """Prepare content for SINGLE mode (1 user + optional partner)"""
        logger.info("Preparing SINGLE mode generation")
        
        user_path = self._validate_and_get_path(user_image_path, "User")
        user_image = Image.open(user_path)
        logger.debug(f"User image loaded: {user_image.size}")
        
        has_partner = partner_image_path is not None
        contents = [self._create_generation_prompt(prompt, GenerationMode.SINGLE, has_partner), user_image]
        
        if partner_image_path:
            partner_path = self._validate_and_get_path(partner_image_path, "Partner")
            partner_image = Image.open(partner_path)
            logger.debug(f"Partner image loaded: {partner_image.size}")
            contents.append(partner_image)
        
        return contents, prompt
    
    def _prepare_couple_mode(
        self,
        couple_image_path: str,
        prompt: str
    ) -> Tuple[list, str]:
        """Prepare content for COUPLE mode (1 image with both people)"""
        logger.info("Preparing COUPLE mode generation")
        
        couple_path = self._validate_and_get_path(couple_image_path, "Couple")
        couple_image = Image.open(couple_path)
        logger.debug(f"Couple image loaded: {couple_image.size}")
        
        full_prompt = self._create_generation_prompt(prompt, GenerationMode.COUPLE, True)
        contents = [full_prompt, couple_image]
        
        return contents, prompt
    
    def _prepare_multi_angle_mode(
        self,
        user_images: Dict[str, str],
        partner_images: Dict[str, str],
        prompt: str
    ) -> Tuple[list, str]:
        """Prepare content for MULTI_ANGLE mode (multiple user + partner images)"""
        logger.info("Preparing MULTI_ANGLE mode generation")
        
        # Load all user images
        full_prompt = self._create_generation_prompt(prompt, GenerationMode.MULTI_ANGLE, True)
        contents = [full_prompt]
        
        # Add all user images
        logger.info(f"Loading {len(user_images)} user images")
        for angle, path in user_images.items():
            user_path = self._validate_and_get_path(path, f"User {angle}")
            user_img = Image.open(user_path)
            logger.debug(f"User {angle} image loaded: {user_img.size}")
            contents.append(user_img)
        
        # Add all partner images
        logger.info(f"Loading {len(partner_images)} partner images")
        for angle, path in partner_images.items():
            partner_path = self._validate_and_get_path(path, f"Partner {angle}")
            partner_img = Image.open(partner_path)
            logger.debug(f"Partner {angle} image loaded: {partner_img.size}")
            contents.append(partner_img)
        
        return contents, prompt
    
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
            return str(image_path)
    
    def _create_generation_prompt(
        self, 
        template_prompt: str, 
        mode: GenerationMode,
        has_partner: bool = False
    ) -> str:
        """Optimized prompt for Gemini image generation with strict identity preservation"""

        base_prompt = """You are an expert AI photographer creating photorealistic pre-wedding portraits.

    CRITICAL REQUIREMENT - IDENTITY PRESERVATION:
    The generated image MUST contain the exact same people from the reference photos with zero identity modification.
    This is photographic reproduction of real individuals, not character creation or beautification.

    MANDATORY PRESERVATION:
    - Exact face structure and proportions
    - Natural facial asymmetry
    - Authentic skin texture and tone
    - Real eyebrow shape and hairline
    - Distinctive marks (freckles, moles, scars, beard patterns)
    - Eye shape, spacing, and color
    - Nose structure and dimensions
    - Lip shape and fullness
    - Jawline and chin contour
    - Body build and proportions
    """

        # MODE-SPECIFIC INSTRUCTIONS
        if mode == GenerationMode.SINGLE:
            if has_partner:
                mode_instructions = """
    INPUT MODE: Two separate individual images (Person 1 and Person 2)

    IDENTITY LOCK REQUIREMENTS:
    - Person 1 facial features must match Person 1 reference exactly
    - Person 2 facial features must match Person 2 reference exactly
    - Preserve natural height difference between subjects
    - Maintain authentic body proportions for both individuals
    - Keep distinct facial characteristics separate (do not blend or average)
    """
            else:
                mode_instructions = """
    INPUT MODE: Single subject image

    IDENTITY LOCK REQUIREMENTS:
    - Output must contain the exact person from reference
    - All facial features must remain geometrically identical
    - Preserve unique facial characteristics and asymmetries
    - Maintain authentic proportions and contours
    """

        elif mode == GenerationMode.COUPLE:
            mode_instructions = """
    INPUT MODE: One image containing both people together

    IDENTITY LOCK REQUIREMENTS:
    - Preserve both individuals' unique facial identities
    - Maintain natural height and body proportion differences
    - Keep authentic spatial relationship and chemistry
    - Do not average or blend facial features between subjects
    - Preserve each person's distinct characteristics independently
    """

        elif mode == GenerationMode.MULTI_ANGLE:
            mode_instructions = """
    INPUT MODE: Multiple reference images showing each person from different angles

    IDENTITY LOCK REQUIREMENTS:
    - Construct accurate 3D facial geometry from all provided angles
    - Front view: locks inner facial feature geometry (eye spacing, nose shape, lip contour)
    - Side/profile view: locks nose bridge, forehead slope, jaw angle, chin projection
    - Three-quarter view: locks facial depth, cheekbone position, head proportion
    - Synthesize consistent identity across all angles without drift or variation
    - Preserve micro-details visible in any reference angle (beard texture, facial asymmetry)
    """

        scene_requirements = f"""
    SCENE INSTRUCTIONS:
    {template_prompt}

    ALLOWED MODIFICATIONS:
    - Clothing and outfit styling (must suit the scene)
    - Background environment and setting
    - Lighting setup and quality
    - Pose and body positioning
    - Camera angle and framing
    - Color grading and cinematic tone

    STRICTLY PROHIBITED:
    - Any alteration to facial geometry or proportions
    - Facial symmetry enhancement or smoothing
    - Eye, lip, or nose size modifications
    - Face or body slimming/reshaping
    - Age, ethnicity, or skin tone changes
    - Beauty filters or AI enhancement
    - Generic or idealized facial features
    - Identity drift or feature averaging
    - Creating new faces or replacing subjects

    TECHNICAL SPECIFICATIONS:
    - Output resolution: 4K minimum
    - Depth of field: shallow (sharp subject, soft background)
    - Lighting style: soft cinematic wedding photography
    - Image type: photorealistic, real camera simulation
    - Composition: professional portrait framing standards

    QUALITY VERIFICATION CHECKLIST:
    - Subject appears identical to reference images
    - All facial features geometrically unchanged
    - Face proportions accurately maintained
    - Natural asymmetries preserved
    - Distinctive marks present (freckles, scars, etc.)
    - Skin tone matches reference
    - Height differences maintained (if couple)
    - Body types consistent with reference
    - Scene matches template requirements

    FINAL CONSTRAINT:
    If forced to choose between scene aesthetic quality and identity accuracy, always prioritize identity accuracy.
    Generate the exact people from the references, not idealized versions."""

        return base_prompt + mode_instructions + scene_requirements