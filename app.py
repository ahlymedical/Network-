# make_network_zip.py
# usage:
#   python make_network_zip.py "network_data (1).xlsx"

import sys, os, json, zipfile, hashlib
from typing import List
import pandas as pd

def clean_phone(val: object) -> str:
    s = str(val).strip()
    if s.lower() in ("nan", "none", "null"):
        return ""
    if s.endswith(".0"):  # أرقام اتقريت float من الإكسل
        s = s[:-2]
    return s

def main(xlsx_path: str):
    if not os.path.exists(xlsx_path):
        print(f"[!] Excel not found: {xlsx_path}")
        sys.exit(1)

    # قراءة الشيت
    xlsx = pd.ExcelFile(xlsx_path)
    sheet_name = "network_data" if "network_data" in xlsx.sheet_names else xlsx.sheet_names[0]
    df = pd.read_excel(xlsx_path, sheet_name=sheet_name, header=0)
    df.columns = [str(c).strip() for c in df.columns]

    # تحديد أعمدة مطلوبة (أسماء عربية كما في الملف)
    name_col = "اسم مقدم الخدمة" if "اسم مقدم الخدمة" in df.columns else ("مقدم الخدمة" if "مقدم الخدمة" in df.columns else None)
    if name_col is None:
        print("[!] لم يتم العثور على عمود الاسم (اسم مقدم الخدمة/مقدم الخدمة).")
        sys.exit(1)

    required_source_cols = {
        "المنطقة": "governorate",
        "التخصص الرئيسي": "provider_type",
        "التخصص الفرعي": "specialty_sub",
        name_col: "name",
        "عنوان مقدم الخدمة": "address",
    }

    # تأكد من وجود الأعمدة، لو ناقص أنشئ عمود فاضي
    for col in list(required_source_cols.keys()) + ["Telephone1","Telephone2","Telephone3","Telephone4","Hotline"]:
        if col not in df.columns:
            df[col] = ""

    # تخلّص من الصفوف الفارغة
    df = df.dropna(how="all")

    # احتفظ فقط بالصفوف التي تحتوي منطقة واسم
    df = df[(df["المنطقة"].astype(str).str.strip() != "") & (df[name_col].astype(str).str.strip() != "")]

    records = []
    for idx, row in df.iterrows():
        phones: List[str] = []
        for c in ["Telephone1","Telephone2","Telephone3","Telephone4"]:
            p = clean_phone(row.get(c, ""))
            if p not in ("", "0"):
                phones.append(p)

        hotline = clean_phone(row.get("Hotline", ""))
        hotline = hotline if hotline not in ("", "0") else None

        rec = {
            "governorate": str(row.get("المنطقة", "")).strip(),
            "provider_type": str(row.get("التخصص الرئيسي", "")).strip(),
            "specialty_sub": str(row.get("التخصص الفرعي", "")).strip(),
            "name": str(row.get(name_col, "")).strip(),
            "address": str(row.get("عنوان مقدم الخدمة", "")).strip(),
            "phones": phones,
            "hotline": hotline,
            "id": f"row-{idx}",
        }
        records.append(rec)

    # مسارات الإخراج
    out_json = "network_data.json"
    out_json_min = "network_data.min.json"
    out_csv = "network_data.csv"
    out_zip = "network_data_all.zip"

    # JSON منسّق
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

    # JSON مضغوط (minified)
    with open(out_json_min, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, separators=(",", ":"))

    # CSV (phones كقائمة مفصولة بفواصل منقوطة)
    df_out = pd.DataFrame(records)
    df_out["phones"] = df_out["phones"].apply(lambda lst: ";".join(lst) if isinstance(lst, list) else "")
    df_out.to_csv(out_csv, index=False, encoding="utf-8-sig")

    # ZIP
    with zipfile.ZipFile(out_zip, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.write(out_json, arcname=os.path.basename(out_json))
        z.write(out_json_min, arcname=os.path.basename(out_json_min))
        z.write(out_csv, arcname=os.path.basename(out_csv))

    # شوية معلومات للطباعة
    def md5sum(path):
        m = hashlib.md5()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                m.update(chunk)
        return m.hexdigest()

    print("\n[✓] Conversion complete")
    print(f"  Records: {len(records)}")
    print(f"  JSON: {out_json}   ({os.path.getsize(out_json)} bytes)   md5={md5sum(out_json)}")
    print(f"  JSON(min): {out_json_min}   ({os.path.getsize(out_json_min)} bytes)   md5={md5sum(out_json_min)}")
    print(f"  CSV:  {out_csv}   ({os.path.getsize(out_csv)} bytes)   md5={md5sum(out_csv)}")
    print(f"  ZIP:  {out_zip}   ({os.path.getsize(out_zip)} bytes)   md5={md5sum(out_zip)}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python make_network_zip.py \"network_data (1).xlsx\"")
        sys.exit(1)
    main(sys.argv[1])
