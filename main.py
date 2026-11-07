from fastapi import FastAPI,UploadFile,File,Form,HTTPException
import tempfile
from pathlib import Path
from ocr.bodhan_service import load_ocr_model
from pydantic import BaseModel
from services.name_matching_service import classify_name_match

class FieldVerification(BaseModel):
       status:str
       score:float|None
       method:str|None
       reason:str
class VerificationDetails(BaseModel):
       name:FieldVerification
       father_name:FieldVerification
       mother_name:FieldVerification
class VerificationResponse(BaseModel):
       filename:str
       extracted_text:str
       verification:VerificationDetails
       overall_status:str
       overall_verified:bool
       failure_reasons:list[str]

app=FastAPI()
MAX_FILE_SIZE=35*1024*1024
ALLOWED_EXTENSIONS={".jpg",".jpeg",".png"}
@app.post("/verify-birth-certificate", response_model=VerificationResponse)
async def verify_birth_certificate(
    name: str = Form(...,examples=[""]),
    father_name: str = Form(...,examples=[""]),
    mother_name: str = Form(...,examples=[""]),
    file: UploadFile = File(...)
):
        extension=Path(file.filename).suffix.lower()
        if extension not in ALLOWED_EXTENSIONS:
                raise HTTPException(
                        status_code=400,
                        detail="Only JPG,JPEG and PNG files are supported"
                )
        contents = await file.read()
        if not contents:
                raise HTTPException(
                        status_code=400,detail="Uploaded file is empty"
                )
        if len(contents)>MAX_FILE_SIZE:
                raise HTTPException(
                        status_code=400,
                        detail="Maximum file size should be 35 MB"
                )
        temp_path=None
        try:
                with tempfile.NamedTemporaryFile(
                        suffix=extension,
                        delete=False
                )as temp_file:
                        temp_file.write(contents)
                        temp_path=Path(temp_file.name)
                parser=load_ocr_model()
                result=parser.parse(str(temp_path))
                extracted_text=result["markdown"]
                document_blocks=[b["text"] for b in result.get("blocks",[]) if b.get("text")]
                document_blocks.append(extracted_text)

                name_result=classify_name_match(name, document_blocks)
                father_result=classify_name_match(father_name, document_blocks)
                mother_result=classify_name_match(mother_name, document_blocks)

                statuses=[name_result["status"], father_result["status"], mother_result["status"]]
                if "MISMATCH" in statuses:
                        overall_status="MISMATCH"
                elif "MANUAL_REVIEW" in statuses:
                        overall_status="MANUAL_REVIEW"
                else:
                        overall_status="MATCH"

                failure_reasons=[]
                for label, field_result in (
                        ("Child name", name_result),
                        ("Father's name", father_result),
                        ("Mother's name", mother_result),
                ):
                        if field_result["status"] != "MATCH":
                                failure_reasons.append(f"{label}: {field_result['reason']}")

                return{
                        "filename":file.filename,
                        "extracted_text":extracted_text,
                        "verification":{
                                "name":name_result,
                                "father_name":father_result,
                                "mother_name":mother_result
                        },
                        "overall_status":overall_status,
                        "overall_verified":overall_status=="MATCH",
                        "failure_reasons":failure_reasons
                }
        except HTTPException:
                raise
        except Exception as e:
                raise HTTPException(
                        status_code= 500,
                        detail=f"OCR processing failed:{str(e)}"
                )
        finally:
                if temp_path and temp_path.exists():
                        temp_path.unlink()
