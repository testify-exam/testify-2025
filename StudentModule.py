from datetime import datetime
from zoneinfo import ZoneInfo
from fastapi.responses import HTMLResponse,JSONResponse
from fastapi.templating import Jinja2Templates
from more_itertools import raise_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import delete, select, and_, func,update,insert
from typing import List, Optional, Dict, Any
from fastapi import BackgroundTasks, Form, Request, HTTPException, Depends
from typing import List, Dict, Any
from sqlalchemy.orm import selectinload, joinedload
from Database import *
from datetime import datetime as dt, timezone
from pydantic import BaseModel, Field, field_validator


templates = Jinja2Templates(directory="templates")

async def is_team_lead(user_id: int, db: AsyncSession) -> bool:
    result = await db.execute(
        select(User.is_team_lead)
        .where(User.id == user_id)
    )
    value = result.scalar_one_or_none()
    return bool(value == 1) 
async def _get_departments_list(db: AsyncSession):
    result = await db.execute(
        select(Department.id, Department.name).order_by(Department.name)
    )
    return [{"id": d.id, "name": d.name} for d in result.all()]


def require_login(request: Request):
    if not request.session.get("user_id"):
        raise HTTPException(status_code=401, detail="Please log in to access this page.")

async def process_exam_submission(
    attempt_id: int,
    questions: List[Dict[str, Any]],
    form_data: Dict[str, Any],
):
    async with async_session() as db:
        total_score = 0
        response_records = []
        selected_option_ids = []

        for question in questions:
            qid = question["id"]
            answer = form_data.get(f"q_{qid}")
            selected_option_id = int(answer) if answer and answer.isdigit() else None

            if selected_option_id:
                selected_option_ids.append(selected_option_id)

            response_records.append({
                "exam_attempt_id": attempt_id,
                "question_id": qid,
                "selected_option_id": selected_option_id,
            })

        if response_records:
            await db.execute(ExamResponse.__table__.insert().values(response_records))

        if selected_option_ids:
            result = await db.execute(
                select(Option.id, Option.is_correct)
                .where(Option.id.in_(selected_option_ids))
            )
            correct_map = {
                row.id: row.is_correct for row in result.all()
            }

            for record in response_records:
                opt_id = record["selected_option_id"]
                if opt_id and correct_map.get(opt_id):
                    total_score += 1

        await db.execute(
            update(ExamAttempt)
            .where(ExamAttempt.id == attempt_id)
            .values(
                score=total_score,
                end_time=datetime.utcnow(),
                status="submitted",
            )
        )

        await db.commit()



async def get_current_student_id(request: Request, db: AsyncSession) -> int:
    require_login(request)
    session_user_id = request.session.get("user_id")
    role = request.session.get("role")

    if not session_user_id or role != "student":
        raise HTTPException(status_code=403, detail="Unauthorized")

    try:
        user_id = int(session_user_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid user ID")

    # Optional: verify user exists
    user_exists = await db.execute(select(User.id).where(User.id == user_id))
    if not user_exists.scalars().first():
        raise HTTPException(status_code=404, detail="User not found")

    return user_id


class OptionSchema(BaseModel):
    text: str
    is_correct: bool = Field(default=False)

    @field_validator('text')
    def text_not_empty(cls, v):
        if not v.strip():
            raise ValueError('Option text cannot be empty')
        return v.strip()

class OptionUpdateSchema(BaseModel):
    id: Optional[int] = None        
    text: str
    is_correct: bool = False

    @field_validator('text')
    def not_empty(cls, v):
        if not v.strip():
            raise ValueError("Option text cannot be empty")
        return v.strip()

class CreateExam(BaseModel):
    name: str
    subject: str
    start_time: str  # YYYY-MM-DDTHH:MM local Kolkata
    end_time: str
    duration: int
    department_id: int

    @field_validator('name', 'subject')
    def strip_and_not_empty(cls, v):
        v = v.strip()
        if not v:
            raise ValueError('Name and subject cannot be empty')
        return v

    @field_validator('duration')
    def duration_positive(cls, v):
        if v <= 0:
            raise ValueError('Duration must be positive')
        return v

    @field_validator('start_time', 'end_time')
    def parse_datetime(cls, v):
        try:
            dt_local = dt.fromisoformat(v.replace("Z", "+00:00"))  # but since datetime-local, no Z
            if dt_local.tzinfo is None:
                dt_local = dt_local.replace(tzinfo=ZoneInfo("Asia/Kolkata"))
            utc_dt = dt_local.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
            return utc_dt.isoformat()  
        except ValueError as e:
            raise ValueError(f'Invalid date/time format: {e}')

    @field_validator('department_id')
    def department_int(cls, v):
        if v <= 0:
            raise ValueError('Invalid department ID')
        return v
    
class UpdateExam(BaseModel):
    name: Optional[str] = None
    subject: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    duration: Optional[int] = None
    department_id: Optional[int] = None

    @field_validator('name', 'subject')
    def strip_and_not_empty(cls, v):
        if v is None:
            return None
        v = v.strip()
        if not v:
            raise ValueError('Name and subject cannot be empty')
        return v

    @field_validator('duration')
    def duration_positive(cls, v):
        if v is None:
            return None
        if v <= 0:
            raise ValueError('Duration must be positive')
        return v

    @field_validator('start_time', 'end_time')
    def parse_datetime(cls, v):
        if v is None:
            return None
        try:
            dt_local = dt.fromisoformat(v.replace("Z", "+00:00"))
            if dt_local.tzinfo is None:
                dt_local = dt_local.replace(tzinfo=ZoneInfo("Asia/Kolkata"))
            utc_dt = dt_local.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
            return utc_dt.isoformat()
        except ValueError as e:
            raise ValueError(f'Invalid date/time format: {e}')

    @field_validator('department_id')
    def department_int(cls, v):
        if v is None:
            return None
        if v <= 0:
            raise ValueError('Invalid department ID')
        return v

class OptionCreateSchema(BaseModel):
    text: str
    is_correct: bool = False

    @field_validator('text')
    def not_empty(cls, v):
        return v.strip() or raise_(ValueError("Option text required"))

class CreateQuestion(BaseModel):
    question_text: str
    options: List[OptionCreateSchema]

    @field_validator('question_text')
    def not_empty(cls, v):
        return v.strip() or raise_(ValueError("Question text required"))

    @field_validator('options')
    def validate(cls, v):
        if len(v) < 2:
            raise ValueError("Minimum 2 options")
        if sum(1 for o in v if o.is_correct) != 1:
            raise ValueError("Exactly one correct answer")
        return v

    @field_validator('options')
    def options_valid(cls, v):
        if len(v) < 2:
            raise ValueError('At least 2 options are required')
        correct_count = sum(1 for opt in v if opt.is_correct)
        if correct_count != 1:
            raise ValueError('Exactly one option must be correct')
        if len(set(opt.text for opt in v)) < len(v):
            raise ValueError('Option texts must be unique')
        return v

class UpdateQuestion(BaseModel):
    question_text: Optional[str] = None
    options: Optional[List[OptionUpdateSchema]] = None

    @field_validator('options')
    def validate_options(cls, v):
        if v is not None:
            if len(v) < 2:
                raise ValueError("At least 2 options required")
            correct = sum(1 for o in v if o.is_correct)
            if correct != 1:
                raise ValueError("Exactly one option must be correct")
        return v

    @field_validator('options')
    def options_valid(cls, v):
        if v is None:
            return None
        if len(v) < 2:
            raise ValueError('At least 2 options are required')
        correct_count = sum(1 for opt in v if opt.is_correct)
        if correct_count != 1:
            raise ValueError('Exactly one option must be correct')
        if len(set(opt.text for opt in v)) < len(v):
            raise ValueError('Option texts must be unique')
        return v


async def get_current_user(request: Request, db: AsyncSession):
    require_login(request)
    user_id_str = request.session.get("user_id")
    role = request.session.get("role")
    if not user_id_str or not role:
        raise HTTPException(status_code=401, detail="Unauthorized")
    try:
        user_id = int(user_id_str)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid session")
    
    # Check role authorization
    if role == "student":
        if not await is_team_lead(user_id, db):
            raise HTTPException(status_code=403, detail="Not authorized. Only team leads can create exams.")
    elif role != "teacher":
        raise HTTPException(status_code=403, detail="Not authorized.")
    
    return user_id, role

def parse_exam_times(start_str: str, end_str: str):
    try:
        start_dt = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
        end_dt = datetime.fromisoformat(end_str.replace("Z", "+00:00"))
        if start_dt.tzinfo is None:
            start_dt = start_dt.replace(tzinfo=ZoneInfo("Asia/Kolkata"))
        if end_dt.tzinfo is None:
            end_dt = end_dt.replace(tzinfo=ZoneInfo("Asia/Kolkata"))
        start_utc = start_dt.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
        end_utc = end_dt.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
        return start_utc, end_utc
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid date/time format: {e}")


def init(app):
    @app.get("/student/home", response_class=HTMLResponse)
    async def student_home_page(request: Request):
        require_login(request)
        if request.session.get("role") != "student":
            raise HTTPException(status_code=403, detail="Forbidden")
        return templates.TemplateResponse("student_home.html", {"request": request})
    
    
        # 1. Get current student profile
    @app.get("/api/student/me", response_model=dict)
    async def api_student_profile(
        request: Request,
        db: AsyncSession = Depends(get_db)
    ):
        user_id = await get_current_student_id(request, db)  
        result = await db.execute(
            select(User)
            .options(selectinload(User.department))
            .where(User.id == user_id)
        )
        student = result.scalars().first()

        if not student:
            raise HTTPException(status_code=404, detail="Student not found")

        return {
            "id": student.id,
            "username": student.username,
            "email": student.email,
            "roll_number": student.roll_number,
            "register_number": student.register_number,
            "department": {
                "id": student.department.id,
                "name": student.department.name
            } if student.department else None,
            "is_team_lead": bool(student.is_team_lead),
            "approved": bool(student.approved)
        }


    @app.get("/api/student/exam/{exam_id}/leaderboard")
    async def api_exam_leaderboard(
        exam_id: int,
        request: Request,
        db: AsyncSession = Depends(get_db)
    ):
        user_id = await get_current_student_id(request, db)

        # Verify exam exists and belongs to student's department
        exam_check = await db.execute(
            select(Exam.department_id).where(Exam.id == exam_id)
        )
        exam_dept_id = exam_check.scalars().first()
        if not exam_dept_id:
            raise HTTPException(status_code=404, detail="Exam not found")

        student_dept = await db.execute(
            select(User.department_id).where(User.id == user_id)
        )
        if exam_dept_id != student_dept.scalars().first():
            raise HTTPException(status_code=403, detail="Not authorized")

        # Get completed attempts with public scores
        result = await db.execute(
            select(ExamAttempt, User.username, User.roll_number)
            .join(User, User.id == ExamAttempt.student_id)
            .where(
                ExamAttempt.exam_id == exam_id,
                ExamAttempt.score.is_not(None),
                ExamAttempt.student_id != user_id  # exclude self
            )
            .order_by(ExamAttempt.score.desc().nulls_last())
        )

        leaderboard = []
        for attempt, username, roll_number in result.all():
            score_display = attempt.score if attempt.is_score_public else "Hidden"
            leaderboard.append({
                "username": username or "Anonymous",
                "roll_number": roll_number or "-",
                "score": score_display,
                "rank": None  # can compute later if needed
            })

        # Add current user's score at the end (optional)
        my_attempt = await db.execute(
            select(ExamAttempt).where(
                ExamAttempt.exam_id == exam_id,
                ExamAttempt.student_id == user_id
            )
        )
        my = my_attempt.scalars().first()
        my_score = {
            "username": "You",
            "score": my.score if my and my.score is not None else "Not attempted",
            "is_public": my.is_score_public if my else False
        }

        return {
            "exam_id": exam_id,
            "leaderboard": leaderboard,
            "your_score": my_score
        }


    # 4. Get student's past attempts summary
    @app.get("/api/student/attempts")
    async def api_student_attempts(
        request: Request,
        db: AsyncSession = Depends(get_db)
    ):
        user_id = await get_current_student_id(request, db)

        result = await db.execute(
            select(ExamAttempt, Exam.name, Exam.subject)
            .join(Exam, Exam.id == ExamAttempt.exam_id)
            .where(ExamAttempt.student_id == user_id)
            .order_by(ExamAttempt.start_time.desc())
        )

        attempts = []
        for attempt, exam_name, subject in result.all():
            attempts.append({
                "id": attempt.id,
                "exam_name": exam_name,
                "subject": subject,
                "score": attempt.score,
                "status": attempt.status,
                "start_time": attempt.start_time.isoformat() if attempt.start_time else None,
                "is_score_public": attempt.is_score_public
            })

        return {"attempts": attempts}


    # 5. Get list of exams for dropdown (name + id)
    @app.get("/api/student/exam-list")
    async def api_exam_list(
        request: Request,
        db: AsyncSession = Depends(get_db)
    ):
        user_id = await get_current_student_id(request, db)

        dept_id = await db.execute(
            select(User.department_id).where(User.id == user_id)
        )
        dept_id = dept_id.scalars().first()

        result = await db.execute(
            select(Exam.id, Exam.name)
            .where(Exam.department_id == dept_id)
            .order_by(Exam.name)
        )

        return [{"id": eid, "name": name} for eid, name in result.all()]
            

    @app.get("/student/exam/{exam_id}", response_class=HTMLResponse)
    async def take_exam(
        request: Request,
        exam_id: int,
        db: AsyncSession = Depends(get_db)
    ):
        require_login(request)
        if request.session.get("role") != "student":
            raise HTTPException(status_code=403, detail="Not authorized.")

        student_id = request.session.get("user_id")
        if not student_id:
            raise HTTPException(status_code=401, detail="Unauthorized")

        try:
            student_id = int(student_id)
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail="Invalid user ID")

        now = datetime.now(ZoneInfo("Asia/Kolkata"))

        # Fetch exam with department check + questions + options in ONE query
        exam_result = await db.execute(
            select(Exam)
            .options(
                selectinload(Exam.questions).selectinload(Question.options)
            )
            .where(Exam.id == exam_id)
        )
        exam: Exam = exam_result.scalars().first()

        if not exam:
            raise HTTPException(status_code=404, detail="Exam not found.")

        now = datetime.now(ZoneInfo("Asia/Kolkata"))
        start_time = exam.start_time.replace(tzinfo=ZoneInfo("Asia/Kolkata"))
        end_time = exam.end_time.replace(tzinfo=ZoneInfo("Asia/Kolkata"))

        if now < start_time:
            raise HTTPException(status_code=400, detail="Exam has not started yet.")
        if now > end_time:
            raise HTTPException(status_code=400, detail="Exam has already ended.")


        # Check or create exam attempt atomically
        attempt_result = await db.execute(
            select(ExamAttempt).where(
                and_(
                    ExamAttempt.exam_id == exam_id,
                    ExamAttempt.student_id == student_id
                )
            )
        )
        attempt = attempt_result.scalars().first()

        if not attempt:
            # Create new attempt
            attempt = ExamAttempt(
                exam_id=exam_id,
                student_id=student_id,
                start_time=now,
                status="in_progress"
            )
            db.add(attempt)
            await db.commit()
            await db.refresh(attempt)

        question_data = []
        for question in exam.questions:
            question_data.append({
            "question": {
                "id": question.id,
                "question_text": question.question_text,
            },
            "options": [
                {
                    "id": opt.id,
                    "option_text": opt.option_text,
                    "is_correct": opt.is_correct  
                }
                for opt in question.options
            ]
        })

        exam_duration_seconds = exam.duration * 60

        return templates.TemplateResponse("exam_page.html", {
            "request": request,
            "exam": exam,
            "question_data": question_data,
            "attempt": attempt,
            "exam_duration": exam_duration_seconds,
            "now": now,
        })
        
    
    @app.get("/api/student/exams")
    async def api_student_exams(
        request: Request,
        db: AsyncSession = Depends(get_db),
    ):
        user_id = await get_current_student_id(request, db)
        dept_result = await db.execute(select(User.department_id).where(User.id == user_id))
        department_id = dept_result.scalar_one_or_none()
        if not department_id:
            raise HTTPException(status_code=400, detail="No department assigned")
        now = datetime.now(ZoneInfo("Asia/Kolkata")).replace(tzinfo=None)
        exams_result = await db.execute(
            select(
                Exam,
                func.coalesce(func.count(Question.id), 0).label("q_count")
            )
            .join(Question, Question.exam_id == Exam.id, isouter=True)
            .where(Exam.department_id == department_id)
            .group_by(Exam.id)
            .order_by(Exam.start_time.desc())
        )
        exams_rows = exams_result.all()         
        exam_ids = [exam.id for exam, _ in exams_rows]

        attempts_result = await db.execute(
            select(ExamAttempt).where(
                ExamAttempt.exam_id.in_(exam_ids or [0]),
                ExamAttempt.student_id == user_id
            )
        )
        attempts_map = {a.exam_id: a for a in attempts_result.scalars().all()}

        today_exams = []
        upcoming_exams = []
        ended_exams = []

        for exam, q_count in exams_rows:
            exam_dict = {
                "id": exam.id,
                "name": exam.name,
                "subject": exam.subject,
                "start_time": exam.start_time.isoformat(),
                "end_time": exam.end_time.isoformat(),
                "duration_minutes": exam.duration,
                "question_count": int(q_count),
                "attempt": None,
            }

            if attempt := attempts_map.get(exam.id):
                exam_dict["attempt"] = {
                    "id": attempt.id,
                    "score": attempt.score,
                    "status": attempt.status,
                    "is_score_public": attempt.is_score_public,
                }

            if exam.start_time <= now < exam.end_time:
                today_exams.append(exam_dict)
            elif now < exam.start_time:
                upcoming_exams.append(exam_dict)
            else:
                ended_exams.append(exam_dict)

        return {
            "today_exams": today_exams,
            "upcoming_exams": upcoming_exams,
            "ended_exams": ended_exams,
        }
            

    @app.post("/student/exam/{exam_id}", response_class=JSONResponse)
    async def submit_exam(
        request: Request,
        exam_id: int,
        background_tasks: BackgroundTasks,
        db: AsyncSession = Depends(get_db)
    ):
        require_login(request)

        if request.session.get("role") != "student":
            raise HTTPException(status_code=403, detail="Not authorized.")

        try:
            student_id = int(request.session.get("user_id"))
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="Invalid user ID")

        form_data = await request.form()
        responses_dict = dict(form_data)

        exam_result = await db.execute(
            select(Exam)
            .options(selectinload(Exam.questions).selectinload(Question.options))
            .where(Exam.id == exam_id)
        )
        exam = exam_result.scalars().first()
        if not exam:
            raise HTTPException(status_code=404, detail="Exam not found.")

        attempt_result = await db.execute(
            select(ExamAttempt).where(
                and_(ExamAttempt.exam_id == exam_id,
                    ExamAttempt.student_id == student_id)
            )
        )
        attempt = attempt_result.scalars().first()
        if not attempt:
            raise HTTPException(status_code=400, detail="No active exam attempt found.")

        if attempt.status == "submitted":
            return JSONResponse(
                {"error": "You have already submitted this exam."},
                status_code=400
            )

        # Convert ORM objects to dicts
        parsed_questions = [
            {
                "id": q.id,
                "options": [{"id": o.id, "is_correct": o.is_correct} for o in q.options]
            }
            for q in exam.questions
        ]

        # Pass correct args
        background_tasks.add_task(
            process_exam_submission,
            attempt.id,
            parsed_questions,
            responses_dict,
        )

        return JSONResponse(
            {"message": "Exam submitted successfully! Results will be updated soon."},
            status_code=202
        )


  
    @app.get("/student/exam/{exam_id}/result", response_class=HTMLResponse)
    async def exam_results(
        request: Request,
        exam_id: int,
        db: AsyncSession = Depends(get_db)
    ):
        require_login(request)
        if request.session.get("role") != "student":
            raise HTTPException(status_code=403, detail="Not authorized.")

        student_id = request.session.get("user_id")
        if not student_id:
            raise HTTPException(status_code=401, detail="Unauthorized")
        try:
            student_id = int(student_id)
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail="Invalid session")

        # === 1. Get exam (validate existence + department access if needed) ===
        exam_result = await db.execute(select(Exam).where(Exam.id == exam_id))
        exam = exam_result.scalars().first()
        if not exam:
            raise HTTPException(status_code=404, detail="Exam not found.")

        # === 2. Get student's attempt ===
        attempt_result = await db.execute(
            select(ExamAttempt)
            .where(
                and_(
                    ExamAttempt.exam_id == exam_id,
                    ExamAttempt.student_id == student_id
                )
            )
        )
        attempt = attempt_result.scalars().first()
        if not attempt:
            raise HTTPException(status_code=400, detail="You haven't attempted this exam.")

        if attempt.status != "submitted" or attempt.score is None:
            raise HTTPException(status_code=400, detail="Results not available yet.")

        # === 3. Get all questions with options and student's responses in ONE query ===
        questions_result = await db.execute(
            select(Question)
            .options(
                selectinload(Question.options),
                selectinload(Question.responses).joinedload(ExamResponse.selected_option)
            )
            .where(Question.exam_id == exam_id)
            .order_by(Question.id)
        )
        questions = questions_result.scalars().all()

        results = []
        for question in questions:
            # Find student's response
            student_response = None
            for resp in question.responses:
                if resp.exam_attempt_id == attempt.id:
                    student_response = resp
                    break

            student_option = student_response.selected_option if student_response else None
            correct_option = next((opt for opt in question.options if opt.is_correct), None)

            results.append({
                "question": question,
                "correct_option": correct_option,
                "student_option": student_option,
                "is_correct": student_option and student_option.is_correct if student_option else False
            })

        return templates.TemplateResponse("exam_results.html", {
            "request": request,
            "exam": exam,
            "attempt": attempt,
            "results": results,
            "total_questions": len(questions),
            "score": attempt.score,
        })
        

    @app.post("/student/toggle-score-privacy")
    async def toggle_score_privacy(
        request: Request,
        attempt_id: int = Form(...),
        is_public: str = Form(...),
        db: AsyncSession = Depends(get_db)
    ):
        require_login(request)

        if request.session.get("role") != "student":
            raise HTTPException(status_code=403, detail="Not authorized.")

        try:
            user_id = int(request.session.get("user_id"))
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail="Invalid user ID.")

        # Convert string "true"/"false" → boolean → int (since DB uses Integer 0/1)
        try:
            new_is_public = is_public.lower() == "true"
        except AttributeError:
            raise HTTPException(status_code=400, detail="is_public must be 'true' or 'false'")

        result = await db.execute(
            update(ExamAttempt)
            .where(
                and_(
                    ExamAttempt.id == attempt_id,
                    ExamAttempt.student_id == user_id
                )
            )
            .values(is_score_public=new_is_public)
            .returning(ExamAttempt.id)
        )

        updated = result.scalar_one_or_none()

        if not updated:
            raise HTTPException(
                status_code=404,
                detail="Attempt not found or you don't have permission to modify it."
            )

        await db.commit()

        return JSONResponse(content={"status": "success"})


    @app.get("/api/exams/{exam_id}/questions/", response_class=JSONResponse)
    async def list_questions(
        request: Request,
        exam_id: int,
        db: AsyncSession = Depends(get_db)
    ):
        user_id, _ = await get_current_user(request, db)

        exam_check = await db.execute(
            select(Exam.id).where(and_(Exam.id == exam_id, Exam.teacher_id == user_id))
        )
        if not exam_check.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Exam not found or access denied.")

        stmt = (
            select(Question)
            .options(selectinload(Question.options))
            .where(Question.exam_id == exam_id)
            .order_by(Question.id)
        )
        result = await db.execute(stmt)
        questions = result.scalars().all()

        questions_data = [
            {
                "id": q.id,
                "question_text": q.question_text,
                "options": [
                    {"id": opt.id, "text": opt.option_text, "is_correct": opt.is_correct}
                    for opt in q.options
                ],
            }
            for q in questions
        ]

        # Also return basic exam info for the modal title
        exam = await db.get(Exam, exam_id)
        return {
            "exam": {"id": exam.id, "name": exam.name},
            "questions": questions_data
        }
        

    @app.post("/api/exams/{exam_id}/questions/", response_class=JSONResponse)
    async def add_question(
        request: Request,
        exam_id: int,
        payload: CreateQuestion,
        db: AsyncSession = Depends(get_db)
    ):
        user_id, _ = await get_current_user(request, db)

        exam = await db.get(Exam, exam_id)
        if not exam or exam.teacher_id != user_id:
            raise HTTPException(404, "Exam not found")


        q = Question(exam_id=exam_id, question_text=payload.question_text.strip())
        db.add(q)
        await db.flush()  

        options_data = [
            {"question_id": q.id, "option_text": opt.text, "is_correct": opt.is_correct}
            for opt in payload.options
        ]
        await db.execute(insert(Option), options_data)
        await db.commit()

        return {"question_id": q.id, "message": "Question added"}

    @app.put("/api/exams/{exam_id}/", response_class=JSONResponse)
    async def update_exam(
        request: Request,
        exam_id: int,
        exam_update: UpdateExam,
        db: AsyncSession = Depends(get_db)
    ):
        user_id, _ = await get_current_user(request, db)

        exam_result = await db.execute(
            select(Exam).where(
                and_(
                    Exam.id == exam_id,
                    Exam.teacher_id == user_id
                )
            )
        )
        exam = exam_result.scalars().first()
        if not exam:
            raise HTTPException(status_code=404, detail="Exam not found or you don't have access.")
        
        # Parse times
        if exam_update.start_time or exam_update.end_time:
            start_utc, end_utc = parse_exam_times(exam_update.start_time or exam.start_time.isoformat(), exam_update.end_time or exam.end_time.isoformat())
        else:
            start_utc, end_utc = exam.start_time, exam.end_time
        
        if end_utc <= start_utc:
            raise HTTPException(status_code=400, detail="End time must be after start time.")
        duration = exam_update.duration or exam.duration
        if (end_utc - start_utc).total_seconds() / 60 < duration:
            raise HTTPException(status_code=400, detail="Duration cannot exceed exam window.")

        if exam_update.department_id:
            dept_check = await db.execute(
                select(Department.id).where(Department.id == exam_update.department_id)
            )
            if not dept_check.scalar_one_or_none():
                raise HTTPException(status_code=400, detail="Selected department does not exist.")
        
        # Update fields
        for key, value in exam_update.dict(exclude_unset=True).items():
            if key == 'start_time':
                setattr(exam, 'start_time', start_utc)
            elif key == 'end_time':
                setattr(exam, 'end_time', end_utc)
            else:
                setattr(exam, key, value)
        
        try:
            await db.commit()
        except Exception:
            await db.rollback()
            raise HTTPException(status_code=500, detail="Failed to update exam.")
        
        return JSONResponse(content={"message": "Exam updated successfully"})

    @app.put("/api/questions/{question_id}/", response_class=JSONResponse)
    async def update_question(
        request: Request,
        question_id: int,
        data: UpdateQuestion,
        db: AsyncSession = Depends(get_db)
    ):
        user_id, _ = await get_current_user(request, db)

        # Verify ownership
        q_result = await db.execute(
            select(Question).options(joinedload(Question.exam))
            .where(Question.id == question_id)
        )
        question = q_result.scalars().first()
        if not question or question.exam.teacher_id != user_id:
            raise HTTPException(status_code=404, detail="Question not found or access denied.")

        updated = False

        if data.question_text is not None:
            question.question_text = data.question_text.strip()
            updated = True

        if data.options is not None:
            # Delete old options
            await db.execute(delete(Option).where(Option.question_id == question_id))
            # Insert new ones
            options_data = [
                {"question_id": question_id, "option_text": opt.text, "is_correct": opt.is_correct}
                for opt in data.options
            ]
            await db.execute(insert(Option), options_data)
            updated = True

        if not updated:
            raise HTTPException(status_code=400, detail="Nothing to update")

        await db.commit()
        return {"message": "Question updated successfully"}


    @app.delete("/api/exams/{exam_id}/", response_class=JSONResponse)
    async def delete_exam(
        request: Request,
        exam_id: int,
        db: AsyncSession = Depends(get_db)
    ):
        user_id, _ = await get_current_user(request, db)

        # Load exam with teacher info for ownership check
        exam = await db.get(Exam, exam_id, options=[joinedload(Exam.teacher)])
        if not exam:
            raise HTTPException(status_code=404, detail="Exam not found.")
        
        if exam.teacher_id != user_id:
            raise HTTPException(status_code=403, detail="Access denied: You can only delete your own exams.")

        try:
            await db.execute(
                delete(ExamResponse).where(ExamResponse.exam_attempt_id.in_(
                    select(ExamAttempt.id).where(ExamAttempt.exam_id == exam_id)
                ))
            )

            await db.execute(
                delete(ExamResponse).where(ExamResponse.question_id.in_(
                    select(Question.id).where(Question.exam_id == exam_id)
                ))
            )
            await db.execute(
                delete(Option).where(Option.question_id.in_(
                    select(Question.id).where(Question.exam_id == exam_id)
                ))
            )
            await db.execute(delete(ExamAttempt).where(ExamAttempt.exam_id == exam_id))
            await db.execute(delete(Question).where(Question.exam_id == exam_id))
            await db.delete(exam)
            await db.commit()

        except Exception as e:
            await db.rollback()
            raise HTTPException(status_code=500, detail="Failed to delete exam and all related data.")

        return JSONResponse(content={"message": "Exam and all related data deleted successfully"})
        
    @app.delete("/api/questions/{question_id}/", response_class=JSONResponse)
    async def delete_question(
        request: Request,
        question_id: int,
        db: AsyncSession = Depends(get_db)
    ):
        user_id, _ = await get_current_user(request, db)
        stmt = select(Question).options(selectinload(Question.exam)).where(Question.id == question_id)
        result = await db.execute(stmt)
        question = result.scalars().first()
        
        if not question:
            raise HTTPException(status_code=404, detail="Question not found.")
        
        if question.exam.teacher_id != user_id:
            raise HTTPException(status_code=403, detail="Access denied: You can only delete your own questions.")
        
        try:
            await db.execute(delete(Option).where(Option.question_id == question_id))
            await db.delete(question)
            
            await db.commit()
        except Exception as e:
            await db.rollback()
            raise HTTPException(status_code=500, detail="Failed to delete question and its options.")
        
        return JSONResponse(content={"message": "Question and its options deleted successfully"})
        
    @app.get("/api/departments/", response_class=JSONResponse)
    async def get_departments(db: AsyncSession = Depends(get_db)):
        depts = await _get_departments_list(db)
        return JSONResponse(content={"departments": depts})
    
    

    @app.post("/api/exams/", response_class=JSONResponse)
    async def create_exam(
        request: Request,
        exam: CreateExam,
        db: AsyncSession = Depends(get_db)
    ):
        user_id, _ = await get_current_user(request, db)

        start_utc = dt.fromisoformat(exam.start_time)
        end_utc = dt.fromisoformat(exam.end_time)

        if end_utc <= start_utc:
            raise HTTPException(status_code=400, detail="End time must be after start time.")
        if (end_utc - start_utc).total_seconds() / 60 < exam.duration:
            raise HTTPException(status_code=400, detail="Duration cannot exceed exam window.")

        dept = await db.get(Department, exam.department_id)
        if not dept:
            raise HTTPException(status_code=400, detail="Department does not exist.")

        new_exam = Exam(
            teacher_id=user_id,
            name=exam.name,
            subject=exam.subject,
            start_time=start_utc,
            end_time=end_utc,
            duration=exam.duration,
            department_id=exam.department_id,
        )
        db.add(new_exam)
        await db.commit()
        await db.refresh(new_exam)

        return {"exam_id": new_exam.id, "message": "Exam created successfully"}


    @app.get("/api/exams/", response_class=JSONResponse)
    async def list_exams(
        request: Request,
        db: AsyncSession = Depends(get_db)
    ):
        user_id, _ = await get_current_user(request, db)

        qcount = (
            select(Question.exam_id, func.count("*").label("cnt"))
            .group_by(Question.exam_id)
            .subquery()
        )

        stmt = (
            select(Exam, func.coalesce(qcount.c.cnt, 0).label("questions_count"))
            .outerjoin(qcount, Exam.id == qcount.c.exam_id)
            .options(joinedload(Exam.department))
            .where(Exam.teacher_id == user_id)
            .order_by(Exam.created_at.desc())
        )

        result = await db.execute(stmt)
        rows = result.all()

        exams_data = []
        for exam, qcnt in rows:
            start_local = exam.start_time.replace(tzinfo=timezone.utc) \
                .astimezone(ZoneInfo("Asia/Kolkata")).strftime("%Y-%m-%dT%H:%M")
            end_local = exam.end_time.replace(tzinfo=timezone.utc) \
                .astimezone(ZoneInfo("Asia/Kolkata")).strftime("%Y-%m-%dT%H:%M")

            exams_data.append({
                "id": exam.id,
                "name": exam.name,
                "subject": exam.subject,
                "department_name": exam.department.name if exam.department else "Unknown",
                "department_id": exam.department_id,
                "start_time_local": start_local,
                "end_time_local": end_local,
                "duration": exam.duration,
                "questions_count": int(qcnt),
            })

        return {"exams": exams_data}