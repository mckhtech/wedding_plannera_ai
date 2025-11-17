from dotenv import load_dotenv
import google.generativeai as genai
import os

load_dotenv() 

genai.configure(api_key=os.environ["GEMINI_API_KEY"])

model = genai.GenerativeModel("models/gemini-2.0-flash-exp-image-generation")

response = model.generate_content(
    "a beautiful futuristic city with neon lights, 4k resolution"
)

# Save image
img_bytes = response.generated_images[0]
with open("generated_image.png", "wb") as f:
    f.write(img_bytes)

print("Image saved as generated_image.png")


