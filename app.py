import os
import google.generativeai as genai
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import json
import base64

# تهيئة تطبيق فلاسك لخدمة الملفات الثابتة من مجلد "static"
# أي طلب لـ / سيفتح index.html وأي طلب لـ /icons/some-icon.svg سيفتح الملف من static/icons
app = Flask(__name__, static_folder='static', static_url_path='')
CORS(app)

# قائمة العيادات المتاحة
CLINICS_LIST = """
"الباطنة-العامة", "غدد-صماء-وسكر", "جهاز-هضمي-ومناظير", "باطنة-وقلب", "الجراحة-العامة",
"مناعة-وروماتيزم", "نساء-وتوليد", "أنف-وأذن-وحنجرة", "الصدر", "أمراض-الذكورة", "الجلدية",
"العظام", "المخ-والأعصاب-باطنة", "جراحة-المخ-والأعصاب", "المسالك-البولية", "الأوعية-الدموية",
"الأطفال", "الرمد", "تغذية-الأطفال", "مناعة-وحساسية-الأطفال", "القلب", "رسم-قلب-بالمجهود-وإيكو",
"جراحة-التجميل", "علاج-البواسير-والشرخ-بالليزر", "الأسنان", "السمعيات", "أمراض-الدم"
"""

# المسار الخاص بصفحة الموقع الرئيسية
@app.route('/')
def serve_index():
    return send_from_directory('static', 'index.html')

# المسار الخاص بتوصية العيادات بناءً على الأعراض
@app.route("/api/recommend", methods=["POST"])
def recommend_clinic():
    try:
        data = request.get_json()
        symptoms = data.get('symptoms')
        if not symptoms:
            return jsonify({"error": "Missing symptoms"}), 400
        
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            print("CRITICAL ERROR: GEMINI_API_KEY is not set in environment variables.")
            return jsonify({"error": "Server configuration error."}), 500

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-1.5-flash')

        prompt = f"""
        أنت مساعد طبي خبير ومحترف في مستشفى كبير. مهمتك هي تحليل شكوى المريض بدقة واقتراح أفضل عيادتين بحد أقصى من قائمة العيادات المتاحة.
        قائمة معرفات (IDs) العيادات المتاحة هي: [{CLINICS_LIST}]
        شكوى المريض: "{symptoms}"
        ردك **يجب** أن يكون بصيغة JSON فقط، بدون أي نصوص أو علامات قبله أو بعده، ويحتوي على قائمة اسمها "recommendations" بداخلها عناصر تحتوي على "id" و "reason".
        """
        
        response = model.generate_content(prompt)
        cleaned_text = response.text.strip().replace("```json", "").replace("```", "")
        json_response = json.loads(cleaned_text)
        return jsonify(json_response)
        
    except Exception as e:
        print(f"ERROR in /api/recommend: {str(e)}")
        return jsonify({"error": "An internal server error occurred."}), 500

# المسار الخاص بتحليل التقارير الطبية المرفوعة
@app.route("/api/analyze", methods=["POST"])
def analyze_report():
    try:
        data = request.get_json()
        files_data = data.get('files')
        user_notes = data.get('notes', '')

        if not files_data:
            return jsonify({"error": "Missing files in request"}), 400
        
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            print("CRITICAL ERROR: GEMINI_API_KEY is not set in environment variables.")
            return jsonify({"error": "Server configuration error."}), 500

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-1.5-flash')

        file_parts = []
        for file in files_data:
            file_parts.append({
                "mime_type": file["mime_type"],
                "data": base64.b64decode(file["data"])
            })

        prompt = f"""
        أنت مساعد طبي ذكي ومحلل تقارير طبية في مستشفى مرموق. مهمتك هي تحليل الملفات الطبية (صور، PDF) التي يرفعها المريض وتقديم إرشادات أولية واضحة واحترافية.
        قائمة معرفات (IDs) العيادات المتاحة هي: [{CLINICS_LIST}]
        ملاحظات المريض الإضافية: "{user_notes if user_notes else 'لا يوجد'}"

        المطلوب منك تحليل الملفات المرفقة وتقديم رد بصيغة JSON فقط، بدون أي نصوص أو علامات قبله أو بعده، ويحتوي على الحقول التالية:
        1.  `interpretation`: (String) شرح احترافي ومبسط في نفس الوقت لما يظهر في التقرير. ركز على المؤشرات الرئيسية غير الطبيعية إن وجدت. **لا تقدم تشخيصاً نهائياً أبداً وقل دائماً أن هذه ملاحظات أولية.**
        2.  `temporary_advice`: (Array of strings) قائمة نصائح عامة ومؤقتة يمكن للمريض اتباعها حتى زيارة الطبيب.
        3.  `recommendations`: (Array of objects) قائمة تحتوي على **عيادة واحدة فقط** هي الأنسب للحالة، وتحتوي على `id` و `reason`.

        **مهم جداً:** إذا كانت الملفات غير واضحة، أعد رداً مناسباً في حقل `interpretation` مثل "الملفات المرفقة غير واضحة أو لا تحتوي على معلومات طبية يمكن تحليلها." واترك الحقول الأخرى فارغة.
        """
        
        content = [prompt] + file_parts
        response = model.generate_content(content)
        
        cleaned_text = response.text.strip().replace("```json", "").replace("```", "")
        json_response = json.loads(cleaned_text)
        return jsonify(json_response)

    except json.JSONDecodeError:
        print(f"ERROR in /api/analyze: JSONDecodeError from Gemini response. Response text: {response.text}")
        return jsonify({"error": "فشل المساعد الذكي في تكوين رد صالح. قد تكون الملفات غير واضحة."}), 500
    except Exception as e:
        print(f"ERROR in /api/analyze: {str(e)}")
        return jsonify({"error": f"حدث خطأ غير متوقع في الخادم"}), 500

# هذا الجزء يسمح بتشغيل التطبيق محلياً للاختبار إذا أردت
if __name__ == "__main__":
    # عند التشغيل على Cloud Run، سيتم استخدام Gunicorn بدلاً من هذا.
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
