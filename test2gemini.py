import os
from google import genai
from google.genai import types
from PIL import Image, ImageDraw
from dotenv import load_dotenv

load_dotenv() 

MODEL_NAME = "gemini-2.5-flash-image"
INPUT_IMAGE_PATH = "download_man.jpeg"
OUTPUT_IMAGE_PATH = "girl.png"

PROMPT = (
    "Transform the two people in the provided image into a romantic couple on a luxurious tropical beach vacation. "
    "Maintain their facial features and likeness accurately. "
    "Dress them in stylish, light summer resort wear (e.g., linen shirt and shorts for him, flowing sundress for her). "
    "Place them on a pristine white sand beach with crystal-clear turquoise water and lush palm trees in the background. "
    "The lighting should be soft, golden hour sunlight, casting a warm glow. "
    "They should be holding hands or gently embracing, looking lovingly at each other or out at the beautiful scenery. "
    "Ensure the mood is serene, romantic, and joyful, capturing a perfect vacation moment. "
    "Make sure the image is photorealistic, high-resolution, and beautifully composed."
)

# --- Helper Function to Create a Dummy Input Image if Missing ---
def create_dummy_image(path):
    """Creates a simple image for testing if the target file is missing."""
    if not os.path.exists(path):
        print(f"--- 🖼️ Creating dummy image at {path} ---")
        try:
            # Create a simple red square image (512x512)
            img = Image.new('RGB', (512, 512), color='darkred')
            # Draw a simple white circle in the center
            draw = ImageDraw.Draw(img)
            draw.ellipse((100, 100, 412, 412), fill='white', outline='white', width=5)
            img.save(path)
            print("Dummy image created. Replace it with your own image to edit.")
        except Exception as e:
            print(f"Error creating dummy image: {e}")
            return False
    return True

# --- Main Image-to-Image Generation Function ---
def generate_edited_image():
    """Performs the image-to-image generation using the Gemini API."""
    
    # 1. Ensure the input image file exists
    if not create_dummy_image(INPUT_IMAGE_PATH):
        return

    # 2. Check for API Key
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("❌ Error: GEMINI_API_KEY not found in environment variables. Check your .env file.")
        return

    try:
        # 3. Initialize the client
        # The client automatically uses the GEMINI_API_KEY environment variable.
        client = genai.Client(api_key=api_key)

        # 4. Load the input image using PIL
        input_image = Image.open(INPUT_IMAGE_PATH)
        print(f"\nLoaded input image from {INPUT_IMAGE_PATH}. Size: {input_image.size}")
        print(f"Editing prompt: '{PROMPT}'")
        
        # 5. Define the contents (Prompt and Image)
        contents = [
            PROMPT,
            input_image # The GenAI SDK can directly accept a PIL Image object
        ]

        # 6. Define the generation configuration for image output
        config = types.GenerateContentConfig(
            response_modalities=["IMAGE"], # CRUCIAL: Specifies the model should output an image
            image_config=types.ImageConfig(
                aspect_ratio="1:1" # Output image aspect ratio
            )
        )

        print(f"\nSending request to model: {MODEL_NAME}...")

        # 7. Call the API
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=contents,
            config=config
        )

        # 8. Process and Save the Image Response
        if response.candidates and response.candidates[0].content.parts:
            part = response.candidates[0].content.parts[0]
            if hasattr(part, 'inline_data') and part.inline_data:
                # part.as_image() converts the base64 data to a PIL Image object
                generated_image = part.as_image()
                generated_image.save(OUTPUT_IMAGE_PATH)
                print(f"✅ Success! Edited image saved as {OUTPUT_IMAGE_PATH}")
                print("\nCheck your directory for both 'input_image_to_edit.png' and 'output_edited_image.png'.")
            else:
                print("❌ Error: Response did not contain inline image data.")
        else:
            print("❌ Error: No valid candidates or parts found in the response.")

    except Exception as e:
        print(f"--- A Fatal Error Occurred ---")
        print(f"Error details: {e}")
        print("Please verify the model name, API key validity, and ensure all libraries are installed.")

if __name__ == "__main__":
    generate_edited_image()