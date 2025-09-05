import os
import json
import re
import pandas as pd
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import google.generativeai as genai
from pathlib import Path

# --- 1. الإعدادات الأولية ---

# تعديل هام: تحديد المجلد الذي يحتوي على ملفات الواجهة الأمامية (HTML, CSS, JS)
# افترضت أن اسمه 'public'. إذا كان اسم المجلد مختلفًا، قم بتغييره هنا.
STATIC_DIR = 'public'

# تهيئة تطبيق فلاسك مع تحديد المجلد الصحيح
app = Flask(__name__, static_folder=STATIC_DIR, static_url_path='')
CORS(app)

# إعداد مفتاح Gemini API
try:
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    if not GEMINI_API_KEY:
        raise ValueError("لم يتم العثور على مفتاح GEMINI_API_KEY في متغيرات البيئة.")
    genai.configure(api_key=GEMINI_API_KEY)
except Exception as e:
    print(f"خطأ في إعداد Gemini API: {e}")

# --- 2. تحميل ومعالجة البيانات ---

NETWORK_DF = pd.DataFrame()
UNIQUE_SPECIALTIES = []

def load_network_data():
    """تحميل بيانات الشبكة الطبية من ملف JSON إلى DataFrame عند بدء التشغيل"""
    global NETWORK_DF, UNIQUE_SPECIALTIES
    # تأكد من أن المسار صحيح بالنسبة لمكان تشغيل Gunicorn
    json_path = Path(__file__).parent / "network_data.json"
    if json_path.exists():
        try:
            print(f"[*] يتم تحميل بيانات الشبكة من {json_path}...")
            NETWORK_DF = pd.read_json(json_path)
            specialties = pd.concat([NETWORK_DF['provider_type'], NETWORK_DF['specialty_sub']]).dropna().unique()
            UNIQUE_SPECIALTIES = [s for s in specialties if s and "جميع" not in s]
            print(f"[✓] تم تحميل {len(NETWORK_DF)} سجل بنجاح.")
        except Exception as e:
            print(f"[!] خطأ أثناء تحميل أو معالجة {json_path}: {e}")
    else:
        print(f"[!] تحذير: ملف البيانات {json_path} غير موجود. خاصية البحث لن تعمل.")

# --- 3. نماذج الذكاء الاصطناعي ---

text_model = None
vision_model = None

def get_text_model():
    global text_model
    if text_model is None and GEMINI_API_KEY:
        text_model = genai.GenerativeModel('gemini-1.5-flash')
    return text_model

def get_vision_model():
    global vision_model
    if vision_model is None and GEMINI_API_KEY:
        vision_model = genai.GenerativeModel('gemini-1.5-flash')
    return vision_model
    
def clean_json_response(text):
    """محاولة تنظيف استجابة النموذج لاستخراج JSON صالح"""
    match = re.search(r'```json\s*(\{.*?\})\s*```', text, re.DOTALL)
    if match:
        return match.group(1)
    try:
        start = text.index('{')
        end = text.rindex('}') + 1
        return text[start:end]
    except ValueError:
        return None

# --- 4. الواجهات البرمجية (API Endpoints) ---

@app.route('/')
def index():
    """عرض ملف الواجهة الأمامية الرئيسي من المجلد المحدد"""
    # تعديل هام: التأكد من أنه يخدم الملف من المجلد الصحيح
    return send_from_directory(app.static_folder, 'index.html')

@app.route('/api/symptoms-search', methods=['POST'])
def symptoms_search():
    """API لتحليل الأعراض والموقع وإرجاع مقدمي الخدمة المناسبين"""
    if not GEMINI_API_KEY:
        return jsonify({"error": "خدمة المساعد الذكي غير متاحة حالياً."}), 503

    data = request.get_json()
    if not data or 'symptoms' not in data or 'location' not in data:
        return jsonify({"error": "البيانات المرسلة غير كاملة."}), 400

    symptoms = data['symptoms']
    location = data['location']

    if NETWORK_DF.empty:
        return jsonify({"error": "قاعدة بيانات الشبكة الطبية غير متاحة."}), 500

    try:
        prompt = f"""
        أنت مساعد طبي متخصص في توجيه المرضى. بناءً على الأعراض التالية: "{symptoms}"، قم بتحديد التخصص الطبي الأنسب.
        يجب أن تختار تخصصًا واحدًا فقط من القائمة التالية: {json.dumps(UNIQUE_SPECIALTIES, ensure_ascii=False)}.
        وقدم نصيحة أولية قصيرة جداً (جملة واحدة) باللغة العربية.

        أريد الإجابة بصيغة JSON فقط، بالشكل التالي ولا شيء غيره:
        {{
          "recommended_specialty": "التخصص المختار من القائمة",
          "initial_advice": "نصيحة أولية موجزة."
        }}
        """
        
        model = get_text_model()
        if not model:
            raise Exception("نموذج اللغة غير مهيأ.")
        response = model.generate_content(prompt)
        
        cleaned_response_text = clean_json_response(response.text)
        if not cleaned_response_text:
             raise Exception("لم يتمكن النموذج من إرجاع JSON صالح.")
        
        ai_result = json.loads(cleaned_response_text)
        recommended_specialty = ai_result.get("recommended_specialty", "")
        initial_advice = ai_result.get("initial_advice", "")

        location_df = NETWORK_DF[
            NETWORK_DF['governorate'].str.contains(location, case=False, na=False) |
            NETWORK_DF['address'].str.contains(location, case=False, na=False)
        ]

        best_match_df = location_df[
            location_df['provider_type'].str.contains(recommended_specialty, case=False, na=False) |
            location_df['specialty_sub'].str.contains(recommended_specialty, case=False, na=False)
        ]

        if not best_match_df.empty:
            best_match = best_match_df.head(1).to_dict(orient='records')
            other_results = best_match_df.iloc[1:].to_dict(orient='records')
        else:
            best_match = location_df.head(1).to_dict(orient='records')
            other_results = location_df.iloc[1:].to_dict(orient='records')

        return jsonify({
            "initial_advice": initial_advice,
            "best_match": best_match,
            "other_results": other_results
        })

    except Exception as e:
        print(f"خطأ في API البحث بالأعراض: {e}")
        return jsonify({"error": f"حدث خطأ أثناء معالجة طلبك: {e}"}), 500


@app.route('/api/analyze', methods=['POST'])
def analyze_reports():
    """API لتحليل التقارير الطبية المرفوعة"""
    if not GEMINI_API_KEY:
        return jsonify({"error": "خدمة المساعد الذكي غير متاحة حالياً."}), 503
        
    data = request.get_json()
    if not data or 'files' not in data or not isinstance(data['files'], list):
        return jsonify({"error": "البيانات المرسلة غير صالحة أو لا تحتوي على ملفات."}), 400

    try:
        model_parts = []
        prompt = f"""
        أنت مساعد طبي ذكي متخصص في تحليل التقارير الطبية. قم بتحليل الصور أو ملفات PDF المرفقة.
        مهمتك هي تقديم شرح مبسط، نصائح مؤقتة، والتخصص الموصى به.
        
        أريد الإجابة باللغة العربية وبصيغة JSON فقط، بالشكل التالي ولا شيء غيره:
        {{
          "interpretation": "شرح مبسط وواضح لنتائج التقرير.",
          "temporary_advice": [
            "نصيحة أولى على شكل جملة.",
            "نصيحة ثانية على شكل جملة.",
            "نصيحة ثالثة على شكل جملة."
          ],
          "recommended_specialty": "اسم التخصص الطبي الوحيد الذي يجب على المريض زيارته."
        }}
        
        تذكر: لا تقدم أي نص قبل أو بعد كائن الـ JSON.
        """
        model_parts.append(prompt)

        for file_info in data['files']:
            mime_type = file_info.get('mime_type')
            base64_data = file_info.get('data')
            if mime_type and base64_data:
                model_parts.append({'mime_type': mime_type, 'data': base64_data})

        if len(model_parts) < 2:
             return jsonify({"error": "لم يتم إرسال أي ملفات صالحة للتحليل."}), 400

        model = get_vision_model()
        if not model:
            raise Exception("نموذج الرؤية غير مهيأ.")
        response = model.generate_content(model_parts)
        
        cleaned_response_text = clean_json_response(response.text)
        if not cleaned_response_text:
            raise Exception("لم يتمكن النموذج من إرجاع JSON صالح.")
            
        ai_result = json.loads(cleaned_response_text)

        return jsonify(ai_result)

    except Exception as e:
        print(f"خطأ في API تحليل التقارير: {e}")
        return jsonify({"error": f"حدث خطأ أثناء تحليل التقرير: {e}"}), 500

# --- 5. تشغيل التطبيق ---

# تحميل البيانات عند بدء تشغيل Gunicorn
load_network_data()

if __name__ == '__main__':
    # هذا الجزء للتشغيل المحلي فقط
    app.run(debug=True, port=5000)
