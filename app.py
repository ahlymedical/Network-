import os
import google.generativeai as genai
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import json
import base64
import pandas as pd # <-- تم استيراد مكتبة باندا للتعامل مع الملفات

# This app is designed to serve a static index.html file and provide AI-powered APIs.
# It will serve the main page from the 'static' folder.
app = Flask(__name__, static_folder='static', static_url_path='')
CORS(app)

# --- تحميل بيانات الشبكة الطبية من ملف CSV ---
# يتم تحميل البيانات مرة واحدة عند بدء تشغيل التطبيق لتحسين الأداء
try:
    # تأكد من أن اسم الملف مطابق للملف الذي لديك
    network_df = pd.read_csv('network_data.csv')
    # تحويل البيانات إلى صيغة JSON لتكون جاهزة للإرسال
    NETWORK_DATA_JSON = network_df.to_dict(orient='records')
    print("تم تحميل بيانات الشبكة الطبية بنجاح.")
except FileNotFoundError:
    print("خطأ: لم يتم العثور على ملف 'network_data.csv'. سيتم استخدام بيانات فارغة.")
    NETWORK_DATA_JSON = []
except Exception as e:
    print(f"حدث خطأ أثناء قراءة ملف CSV: {e}")
    NETWORK_DATA_JSON = []
# -------------------------------------------------


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

# --- نقطة وصول جديدة لجلب بيانات الشبكة ---
@app.route('/api/network-data', methods=['GET'])
def get_network_data():
    """
    هذه هي نقطة النهاية الجديدة التي ترسل بيانات الشبكة
    الموجودة في ملف CSV إلى الواجهة الأمامية.
    """
    return jsonify(NETWORK_DATA_JSON)
# -----------------------------------------


@app.route("/api/recommend", methods=["POST"])
def recommend_specialty():
    """
    Analyzes patient symptoms and recommends the most suitable medical specialty.
    This functionality remains unchanged.
    """
    data = request.get_json()
    symptoms = data.get("symptoms", "")
    
    if not symptoms:
        return jsonify({"error": "الرجاء إدخال الأعراض."}), 400
        
    try:
        genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))
        model = genai.GenerativeModel('gemini-pro')
        
        prompt = f"""
        بصفتك مساعدًا طبيًا ذكيًا، قم بتحليل الأعراض التالية واقترح التخصص الطبي الأنسب من القائمة المتاحة فقط.
        الأعراض: \"{symptoms}\"
        قائمة التخصصات المتاحة: [{AVAILABLE_SPECIALTIES}]

        المطلوب منك تقديم رد بصيغة JSON فقط، بدون أي علامات، يحتوي على الحقول التالية:
        1. `id`: (String) اسم التخصص الطبي **المناسب فقط** من القائمة.
        2. `reason`: (String) شرح مبسط باللغة العربية لسبب اختيار هذا التخصص بناءً على الأعراض.

        **هام:** اختر تخصصًا واحدًا فقط. إذا كانت الأعراض غير واضحة، اختر "باطنة" كإجراء احتياطي.
        """
        response = model.generate_content(prompt)
        
        cleaned_text = response.text.strip().replace("```json", "").replace("```", "")
        json_response = json.loads(cleaned_text)
        return jsonify(json_response)
        
    except json.JSONDecodeError:
        print(f"ERROR in /api/recommend: JSONDecodeError. Response text: {response.text}")
        return jsonify({"error": "فشل المساعد الذكي في تكوين رد صالح."}), 500
    except Exception as e:
        print(f"ERROR in /api/recommend: {str(e)}")
        return jsonify({"error": "حدث خطأ غير متوقع."}), 500

@app.route("/api/analyze", methods=["POST"])
def analyze_reports():
    """
    Analyzes uploaded medical reports.
    This functionality remains unchanged.
    """
    try:
        user_notes = request.form.get("user_notes", "")
        files = request.files.getlist("files")

        if not files:
            return jsonify({"error": "يرجى رفع ملف واحد على الأقل."}), 400

        genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))
        model = genai.GenerativeModel('gemini-1.5-flash')

        file_parts = []
        for file in files:
            file_bytes = file.read()
            base64_encoded = base64.b64encode(file_bytes).decode('utf-8')
            file_parts.append({
                "mime_type": file.mimetype,
                "data": base64_encoded
            })
        
        prompt = f"""
        بصفتك مساعدًا طبيًا متخصصًا، قم بتحليل التقارير الطبية المرفقة.
        قائمة التخصصات المتاحة للاقتراح: [{AVAILABLE_SPECIALTIES}]
        ملاحظات المريض الإضافية: \"{user_notes if user_notes else 'لا يوجد'}\"

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
        return jsonify({"error": f"حدث خطأ غير متوقع: {str(e)}"}), 500

if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))
