import os
import google.generativeai as genai
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import json
import base64

# This app is designed to serve a static index.html file and provide AI-powered APIs.
# It will serve the main page from the 'static' folder.
app = Flask(__name__, static_folder='static', static_url_path='')
CORS(app)

# This is a dynamic list of specialties that the AI model can recommend.
# In a real-world scenario, this would be populated from a database.
# For now, it's a comprehensive list based on the provided medical network data.
AVAILABLE_SPECIALTIES = """
"باطنة", "علاج طبيعي", "اسنان", "صيدلية", "قلب واوعية دموية", "جراحة مخ وأعصاب", 
"معمل", "أشعة", "نساء وتوليد", "اطفال", "عظام", "جلدية", "انف واذن وحنجرة", 
"عيون", "صدرية", "جراحة عامة", "مسالك بولية", "مستشفى", "مركز طبي", "بصريات"
"""

@app.route('/')
def serve_index():
    """Serves the main index.html file."""
    # To deploy, you should create a 'static' folder and place the final index.html file inside it.
    return send_from_directory('static', 'index.html')

@app.route("/api/recommend", methods=["POST"])
def recommend_specialty():
    """
    Analyzes patient symptoms and recommends the most suitable medical specialty.
    """
    try:
        data = request.get_json()
        symptoms = data.get('symptoms')
        if not symptoms:
            return jsonify({"error": "Missing symptoms"}), 400
        
        # Securely get API key from environment variables
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            print("CRITICAL ERROR: GEMINI_API_KEY is not set.")
            return jsonify({"error": "Server configuration error."}), 500

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-1.5-flash')

        prompt = f"""
        أنت مساعد طبي خبير ومحترف في شركة خدمات طبية كبرى. مهمتك هي تحليل شكوى المريض بدقة واقتراح أفضل تخصص طبي من القائمة المتاحة.
        قائمة التخصصات المتاحة هي: [{AVAILABLE_SPECIALTIES}]
        شكوى المريض: "{symptoms}"
        
        المطلوب:
        1.  حلل الشكوى بعناية.
        2.  اختر التخصص **الأنسب فقط** من القائمة أعلاه.
        3.  اكتب شرحاً احترافياً ومبسطاً للمريض يوضح سبب اختيار هذا التخصص تحديداً.
        4.  قدم قائمة من ثلاث نصائح أولية وعامة يمكن للمريض اتباعها حتى زيارة الطبيب.
        
        ردك **يجب** أن يكون بصيغة JSON فقط، بدون أي نصوص أو علامات قبله أو بعده، ويحتوي على:
        - `recommendations`: قائمة تحتوي على عنصر واحد فقط به "id" (اسم التخصص) و "reason" (سبب الترشيح).
        - `temporary_advice`: قائمة (array) من ثلاثة (3) أسطر نصائح.
        """
        
        response = model.generate_content(prompt)
        # Clean the response to ensure it's valid JSON
        cleaned_text = response.text.strip().replace("```json", "").replace("```", "")
        json_response = json.loads(cleaned_text)
        return jsonify(json_response)
        
    except Exception as e:
        print(f"ERROR in /api/recommend: {str(e)}")
        return jsonify({"error": "An internal server error occurred."}), 500

@app.route("/api/analyze", methods=["POST"])
def analyze_report():
    """
    Analyzes uploaded medical reports (images, PDFs) and provides an initial interpretation.
    """
    try:
        data = request.get_json()
        files_data = data.get('files')
        user_notes = data.get('notes', '')

        if not files_data:
            return jsonify({"error": "Missing files"}), 400
        
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            print("CRITICAL ERROR: GEMINI_API_KEY is not set.")
            return jsonify({"error": "Server configuration error."}), 500

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-1.5-flash')

        file_parts = []
        for file in files_data:
            # Decode the base64 string sent from the frontend
            file_parts.append({
                "mime_type": file["mime_type"],
                "data": base64.b64decode(file["data"])
            })

        prompt = f"""
        أنت محلل تقارير طبية ذكي في شركة خدمات طبية. مهمتك هي تحليل الملفات الطبية (صور، PDF) وتقديم إرشادات أولية احترافية.
        قائمة التخصصات المتاحة هي: [{AVAILABLE_SPECIALTIES}]
        ملاحظات المريض الإضافية: "{user_notes if user_notes else 'لا يوجد'}"

        المطلوب منك تحليل الملفات وتقديم رد بصيغة JSON فقط، بدون أي علامات، يحتوي على الحقول التالية:
        1.  `interpretation`: (String) شرح احترافي ومبسط لما يظهر في التقرير. ركز على المؤشرات غير الطبيعية. **لا تقدم تشخيصاً نهائياً أبداً وأكد أن هذه ملاحظات أولية.**
        2.  `temporary_advice`: (Array of strings) قائمة من 3 نصائح عامة ومؤقتة.
        3.  `recommendations`: (Array of objects) قائمة تحتوي على **تخصص واحد فقط** هو الأنسب للحالة، وتحتوي على `id` و `reason`.

        **هام:** إذا كانت الملفات غير واضحة، أعد رداً مناسباً في حقل `interpretation` واترك الحقول الأخرى فارغة.
        """
        
        content = [prompt] + file_parts
        response = model.generate_content(content)
        
        cleaned_text = response.text.strip().replace("```json", "").replace("```", "")
        json_response = json.loads(cleaned_text)
        return jsonify(json_response)

    except json.JSONDecodeError:
        print(f"ERROR in /api/analyze: JSONDecodeError. Response text: {response.text}")
        return jsonify({"error": "فشل المساعد الذكي في تكوين رد صالح."}), 500
    except Exception as e:
        print(f"ERROR in /api/analyze: {str(e)}")
        return jsonify({"error": f"حدث خطأ غير متوقع."}), 500

if __name__ == "__main__":
    # Gunicorn will be used in production, this is for local testing.
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))

