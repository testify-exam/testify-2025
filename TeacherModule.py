from datetime import datetime
from zoneinfo import ZoneInfo
from fastapi.responses import HTMLResponse,JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import delete, insert, select, and_, func, not_
from typing import List, Optional, Dict, Any
from fastapi import BackgroundTasks, Form, Path, Request, HTTPException, Depends
from datetime import datetime
from typing import List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, and_
from fastapi import Request, HTTPException, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload, joinedload
from sqlalchemy.exc import NoResultFound
from Database import *

templates = Jinja2Templates(directory="templates")

def require_login(request: Request):
    if not request.session.get("user_id"):
        raise HTTPException(status_code=401, detail="Please log in to access this page.")
    
def require_teacher(request: Request):
    if not request.session.get("user_id") or request.session.get("role") != "teacher":
        raise HTTPException(status_code=403, detail="Not authorized.")

async def is_team_lead(user_id: int, db: AsyncSession) -> bool:
    result = await db.execute(
        select(User.is_team_lead)
        .where(User.id == user_id)
    )
    value = result.scalar_one_or_none()
    return bool(value == 1) 

def init(app):
    @app.get("/teacher/home", response_class=HTMLResponse)
    async def teacher_home(request: Request,db: AsyncSession = Depends(get_db)):

        require_teacher(request)  
        teacher_id = request.session.get("user_id")
        if not teacher_id:
            raise HTTPException(status_code=401, detail="Unauthorized")

        # === 2. Fetch current teacher with department info ===
        teacher_result = await db.execute(
            select(User)
            .options(joinedload(User.department))
            .where(User.id == teacher_id)
        )
        teacher = teacher_result.scalars().first()
        if not teacher:
            raise HTTPException(status_code=404, detail="Teacher not found")


        students_result = await db.execute(
            select(User)
            .options(joinedload(User.department))
            .where(User.role == "student")
            .order_by(User.username)
        )
        students = [
            {
                "id": s.id,
                "username": s.username,
                "roll_number": s.roll_number,
                "register_number": s.register_number,
                "department_id": s.department_id,
                "is_team_lead": s.is_team_lead,
                "department_name": s.department.name if s.department else "None"
            }
            for s in students_result.scalars().unique()
        ]

        departments_result = await db.execute(
            select(Department).order_by(Department.name)
        )
        departments = [
            {"id": d.id, "name": d.name}
            for d in departments_result.scalars().all()
        ]

        exams_result = await db.execute(
            select(Exam)
            .where(Exam.teacher_id == teacher_id)
            .order_by(Exam.created_at.desc())
        )
        exams = exams_result.scalars().all()

        pending_students_result = await db.execute(
            select(User)
            .where(
                and_(
                    User.role == "student",
                    User.approved == 0
                )
            )
            .order_by(User.created_at.desc())
        )
        students_apr = pending_students_result.scalars().all()

        return templates.TemplateResponse("teacher_home.html", {
            "request": request,
            "teacher": teacher,
            "students": students,
            "departments": departments,
            "exams": exams,
            "students_apr": students_apr,
        })



    @app.get("/api/exam-scores", response_class=JSONResponse)
    async def get_exam_scores(
        request: Request,
        exam_id: int,  
        db: AsyncSession = Depends(get_db)
    ):
        require_login(request)

        session_user_id = request.session.get("user_id")
        if not session_user_id:
            raise HTTPException(status_code=401, detail="User not logged in.")

        try:
            user_id = int(session_user_id)
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail="Invalid user ID.")

        if request.session.get("role") != "student":
            raise HTTPException(status_code=403, detail="Not authorized.")

        if not exam_id:
            raise HTTPException(status_code=400, detail="Exam ID is required.")

        # === Fetch current student + department in one query ===
        student_result = await db.execute(
            select(User.department_id, Department.name.label("dept_name"))
            .join(Department, Department.id == User.department_id)
            .where(User.id == user_id)
        )
        student_row = student_result.first()

        if not student_row or student_row.department_id is None:
            raise HTTPException(status_code=400, detail="Student's department is not set.")

        student_department_id = student_row.department_id

        result = await db.execute(
            select(
                ExamAttempt.id.label("attempt_id"),
                ExamAttempt.score,
                ExamAttempt.is_score_public,
                User.username.label("student_name"),
                Exam.name.label("exam_name"),
                Department.id.label("department_id")
            )
            .join(User, User.id == ExamAttempt.student_id)
            .join(Exam, Exam.id == ExamAttempt.exam_id)
            .join(Department, Department.id == User.department_id)
            .where(
                and_(
                    ExamAttempt.exam_id == exam_id,
                    ExamAttempt.student_id != user_id,         
                    Department.id == student_department_id,    
                    ExamAttempt.score.is_not(None)            
                )
            )
            .order_by(ExamAttempt.score.desc().nulls_last())
        )

        rows = result.all()

        exam_scores = []
        for row in rows:
            score_display = row.score if row.is_score_public else "Hidden"
            exam_scores.append({
                "attempt_id": row.attempt_id,
                "username": row.student_name or "Anonymous",
                "exam_name": row.exam_name,
                "score": score_display
            })

        return {"exam_scores": exam_scores}


    @app.post("/teacher/create_exam", response_class=HTMLResponse)
    async def create_exam_post(
        request: Request,
        db: AsyncSession = Depends(get_db),
        exam_name: str = Form(...),
        subject_name: str = Form(...),
        start_time: str = Form(...),        # Expected format: "2025-12-25 14:30"
        end_time: str = Form(...),
        duration: int = Form(...),          # in minutes
        department_id: str = Form(...)
    ):
        require_login(request)

        user_id = request.session.get("user_id")
        role = request.session.get("role")

        if not user_id or not role:
            raise HTTPException(status_code=401, detail="Unauthorized")

        try:
            user_id = int(user_id)
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail="Invalid session")
        if role == "student":
            if not await is_team_lead(user_id, db):
                raise HTTPException(
                    status_code=403,
                    detail="Not authorized. Only team leads can create exams."
                )
        elif role != "teacher":
            raise HTTPException(status_code=403, detail="Not authorized.")
        try:
            department_id_int = int(department_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid department selected.")
        dept_check = await db.execute(
            select(Department.id).where(Department.id == department_id_int)
        )
        if not dept_check.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Selected department does not exist.")
        try:
            start_dt = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
            end_dt = datetime.fromisoformat(end_time.replace("Z", "+00:00"))
            if start_dt.tzinfo is None:
                start_dt = start_dt.replace(tzinfo=ZoneInfo("Asia/Kolkata"))
            if end_dt.tzinfo is None:
                end_dt = end_dt.replace(tzinfo=ZoneInfo("Asia/Kolkata"))
            start_utc = start_dt.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
            end_utc = end_dt.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)

        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Invalid date/time format: {e}")
        if end_utc <= start_utc:
            raise HTTPException(status_code=400, detail="End time must be after start time.")
        if duration <= 0                   : raise HTTPException(status_code=400, detail="Duration must be positive.")
        if (end_utc - start_utc).total_seconds() / 60 < duration:
            raise HTTPException(status_code=400, detail="Duration cannot exceed exam window.")
        new_exam = Exam(
            teacher_id=user_id,
            name=exam_name.strip(),
            subject=subject_name.strip(),
            start_time=start_utc,
            end_time=end_utc,
            duration=duration,
            department_id=department_id_int
        )

        db.add(new_exam)
        
        try:
            await db.flush()  
            await db.commit()
        except Exception as e:
            await db.rollback()
            raise HTTPException(status_code=500, detail="Failed to create exam. Please try again.")

        exam_id = new_exam.id

        return RedirectResponse(
            url=f"/teacher/add_question/{exam_id}",
            status_code=302
        )


    @app.get("/teacher/add_question/{exam_id}", response_class=HTMLResponse)
    async def add_question_get(
        request: Request,
        exam_id: int,
        db: AsyncSession = Depends(get_db)
    ):
        require_login(request)

        role = request.session.get("role")
        user_id = request.session.get("user_id")

        if role == "student":
            if not await is_team_lead(user_id):
                raise HTTPException(status_code=403, detail="Not authorized. Only team leads can create exams.")
        elif role != "teacher":
            raise HTTPException(status_code=403, detail="Not authorized.")

    
        exam_result = await db.execute(
            select(Exam)
            .where(
                and_(
                    Exam.id == exam_id,
                    Exam.teacher_id == int(user_id) 
                )
            )
        )
        exam = exam_result.scalars().first()

        if not exam:
            raise HTTPException(status_code=404, detail="Exam not found or you don't have access.")

        return templates.TemplateResponse(
            "add_question.html",
            {
                "request": request,
                "exam_id": exam_id,
                "exam": exam  
            }
        )


    @app.post("/teacher/add_question/{exam_id}", response_class=HTMLResponse)
    async def add_question_post(
        request: Request,
        exam_id: int,
        question_text: str = Form(...),
        option1: str = Form(...),
        option2: str = Form(...),
        option3: str = Form(...),
        option4: str = Form(...),
        correct_option: int = Form(...),
        db: AsyncSession = Depends(get_db)
    ):
        require_login(request)

        role = request.session.get("role")
        user_id_str = request.session.get("user_id")
        try:
            user_id = int(user_id_str)
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail="Invalid user session.")

        if role == "student":
            if not await is_team_lead(user_id):
                raise HTTPException(status_code=403, detail="Not authorized. Only team leads can create exams.")
        elif role != "teacher":
            raise HTTPException(status_code=403, detail="Not authorized.")

        if correct_option not in (1, 2, 3, 4):
            raise HTTPException(status_code=400, detail="Invalid correct option selected.")

        exam_result = await db.execute(
            select(Exam.id, Exam.teacher_id)
            .where(Exam.id == exam_id)
        )
        exam = exam_result.first()
        if not exam or exam.teacher_id != user_id:
            raise HTTPException(status_code=404, detail="Exam not found or access denied.")

        question_stmt = insert(Question).values(
            exam_id=exam_id,
            question_text=question_text.strip()
        ).returning(Question.id)

        try:
            result = await db.execute(question_stmt)
            question_id = result.scalar_one()
        except Exception as e:
            await db.rollback()
            raise HTTPException(status_code=500, detail="Failed to add question.")

        options = [option1.strip(), option2.strip(), option3.strip(), option4.strip()]
        options_data = [
            {
                "question_id": question_id,
                "option_text": opt,
                "is_correct": (i + 1) == correct_option
            }
            for i, opt in enumerate(options)
            if opt 
        ]

        if len(options_data) < 2:
            await db.rollback()
            raise HTTPException(status_code=400, detail="At least 2 options are required.")

        try:
            await db.execute(insert(Option), options_data)
            await db.commit()
        except Exception as e:
            await db.rollback()
            raise HTTPException(status_code=500, detail="Failed to save options.")

        return templates.TemplateResponse(
            "add_question.html",
            {
                "request": request,
                "exam_id": exam_id,
                "message": "Question added successfully!",
                "exam": exam
            }
        )
        
        

    @app.post("/teacher/approve_students")
    async def approve_students(
        request: Request,
        student_id: int = Form(...),
        db: AsyncSession = Depends(get_db)
    ):
        require_teacher(request)  # your existing decorator/function

        # Security: Ensure the student exists and is actually a student
        result = await db.execute(
            select(User).where(
                and_(
                    User.id == student_id,
                    User.role == "student"
                )
            )
        )
        student = result.scalars().first()

        if not student:
            raise HTTPException(status_code=404, detail="Student not found or not a valid student.")

        # Update approved status
        student.approved = 1

        try:
            await db.commit()
        except Exception as e:
            await db.rollback()
            raise HTTPException(status_code=500, detail=f"Database error while approving student: {str(e)}")

        # Optional: Add notification or log action here in production

        return RedirectResponse(url="/teacher/home", status_code=302)



    @app.get("/teacher/student/{student_id}", response_class=HTMLResponse)
    async def view_student_details(
        request: Request,
        student_id: int,
        db: AsyncSession = Depends(get_db)
    ):
        require_teacher(request)

        # Fetch student with department info (eager load to avoid N+1)
        result = await db.execute(
            select(User)
            .options(
                selectinload(User.department)
            )
            .where(
                and_(
                    User.id == student_id,
                    User.role == "student"  # Security: only allow viewing students
                )
            )
        )
        student: User = result.scalars().first()

        if not student:
            raise HTTPException(status_code=404, detail="Student not found.")

        # Fetch all exam attempts + exam name in a single efficient query
        attempts_result = await db.execute(
            select(ExamAttempt.score, Exam.name)
            .join(Exam, ExamAttempt.exam_id == Exam.id)
            .where(ExamAttempt.student_id == student_id)
            .order_by(ExamAttempt.start_time.desc())
        )

        exams = [
            {
                "name": exam_name,
                "score": score if score is not None else "Not graded yet"
            }
            for score, exam_name in attempts_result.all()
        ]

        return templates.TemplateResponse("student_details.html", {
            "request": request,
            "student": student,
            "exams": exams,
            "department": student.department,
        })




    @app.get("/teacher/edit_exam/{exam_id}", response_class=HTMLResponse)
    async def edit_exam_page(
        request: Request,
        exam_id: int,
        db: AsyncSession = Depends(get_db)
    ):
        require_login(request)
        user_id = request.session.get("user_id")
        role = request.session.get("role")

        if not user_id:
            raise HTTPException(status_code=401, detail="Not logged in")

        if role == "student":
            if not await is_team_lead(user_id):  
                raise HTTPException(
                    status_code=403,
                    detail="Not authorized. Only team leads can edit exams."
                )
        elif role != "teacher":
            raise HTTPException(status_code=403, detail="Not authorized.")

        result = await db.execute(
            select(Exam)
            .where(
                Exam.id == exam_id,
                Exam.teacher_id == int(user_id)  
            )
        )
        exam: Exam | None = result.scalars().first()

        if not exam:
            raise HTTPException(status_code=404, detail="Exam not found or access denied.")

        exam_dict = {
            "id": exam.id,
            "name": exam.name,
            "subject": exam.subject,
            "start_time": exam.start_time.isoformat(),
            "end_time": exam.end_time.isoformat(),
            "duration": exam.duration,
            "department_id": exam.department_id,
            "teacher_id": exam.teacher_id,
        }

        return templates.TemplateResponse(
            "edit_exam.html",
            {
                "request": request,
                "exam": exam_dict,
            }
        )

    @app.post("/teacher/edit_exam/{exam_id}", response_class=HTMLResponse)
    async def edit_exam_update(
        request: Request,
        exam_id: int,
        start_time: str = Form(...),
        end_time: str = Form(...),
        duration: int = Form(...),
        db: AsyncSession = Depends(get_db)
    ):
        require_login(request)
        user_id = request.session.get("user_id")
        role = request.session.get("role")

        if not user_id:
            raise HTTPException(status_code=401, detail="Not logged in")

        if role == "student":
            if not await is_team_lead(user_id):
                raise HTTPException(
                    status_code=403,
                    detail="Not authorized. Only team leads can edit exams."
                )
        elif role != "teacher":
            raise HTTPException(status_code=403, detail="Not authorized.")

        try:
            start_dt = datetime.fromisoformat(start_time)
            end_dt = datetime.fromisoformat(end_time)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid datetime format. Use ISO format.")

        if start_dt >= end_dt:
            raise HTTPException(status_code=400, detail="End time must be after start time.")
        if duration <= 0:
            raise HTTPException(status_code=400, detail="Duration must be positive.")

        result = await db.execute(
            update(Exam)
            .where(
                Exam.id == exam_id,
                Exam.teacher_id == int(user_id)
            )
            .values(
                start_time=start_dt,
                end_time=end_dt,
                duration=duration
            )
            .returning(Exam.id)
        )

        updated_exam = result.scalar_one_or_none()

        if not updated_exam:
            raise HTTPException(
                status_code=404,
                detail="Exam not found or you don't have permission to edit it."
            )

        await db.commit()

        return RedirectResponse(url="/teacher/dashboard", status_code=303)



    @app.get("/teacher/view_results/{exam_id}", response_class=HTMLResponse)
    async def view_exam_results(
        request: Request,
        exam_id: int = Path(..., gt=0),
        db: AsyncSession = Depends(get_db)
    ):
        user_id = request.session.get("user_id")
        role = request.session.get("role")

        if not user_id:
            raise HTTPException(status_code=401, detail="Not authenticated.")

        try:
            user_id = int(user_id)
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail="Invalid session.")

        if role == "student":
            if not await is_team_lead(user_id, db):
                raise HTTPException(
                    status_code=403,
                    detail="Not authorized. Only team leads can view results."
                )
        elif role != "teacher":
            raise HTTPException(status_code=403, detail="Not authorized.")

        exam_result = await db.execute(
            select(Exam)
            .options(selectinload(Exam.department))
            .where(Exam.id == exam_id)
        )
        exam: Exam = exam_result.scalar_one_or_none()

        if not exam:
            raise HTTPException(status_code=404, detail="Exam not found.")

        department_id = exam.department_id
        if not department_id:
            raise HTTPException(status_code=500, detail="Exam has no department assigned.")

        students_result = await db.execute(
            select(User.id, User.username)
            .where(
                and_(
                    User.role == "student",
                    User.department_id == department_id
                )
            )
            .order_by(User.username)
        )
        students = students_result.all() 

        if not students:

            return templates.TemplateResponse("view_exam_results.html", {
                "request": request,
                "results": [],
                "exam_id": exam_id,
                "exam_name": exam.name,
                "submitted_count": 0,
                "not_attended_count": 0,
            })

        student_ids = [s[0] for s in students]

        attempts_result = await db.execute(
            select(ExamAttempt.student_id, ExamAttempt.score, ExamAttempt.status)
            .where(
                and_(
                    ExamAttempt.exam_id == exam_id,
                    ExamAttempt.student_id.in_(student_ids)
                )
            )
        )
        attempts_raw = attempts_result.all()

        attempts_by_student = {
            row.student_id: {"score": row.score, "status": row.status}
            for row in attempts_raw
        }

        results = []
        submitted_count = 0
        not_attended_count = 0

        for student_id, username in students:
            attempt = attempts_by_student.get(student_id)

            if not attempt:
                status = "not attended"
                score = None
                not_attended_count += 1
            else:
                status = attempt.get("status") or "not attended"
                score = attempt.get("score")
                if status == "submitted":
                    submitted_count += 1
                elif status == "not attended":
                    not_attended_count += 1

            results.append({
                "student_id": student_id,
                "username": username or f"User_{student_id}",
                "score": score,
                "status": status,
            })

        results.sort(key=lambda x: (x["username"] or "").lower())

        return templates.TemplateResponse("view_exam_results.html", {
            "request": request,
            "results": results,
            "exam_id": exam_id,
            "exam_name": getattr(exam, "name", "Unknown Exam"),
            "submitted_count": submitted_count,
            "not_attended_count": not_attended_count,
            "total_students": len(students),
        })



    @app.post("/teacher/reset_exam_status/{exam_id}/{student_id}")
    async def reset_exam_status(
        request: Request,
        exam_id: int,
        student_id: int,
        db: AsyncSession = Depends(get_db)
    ):
        require_login(request)

        user_id = request.session.get("user_id")
        role = request.session.get("role")

        if not user_id:
            raise HTTPException(status_code=401, detail="Not authenticated.")

        try:
            user_id = int(user_id)
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail="Invalid user session.")
        if role == "student":
            if not await is_team_lead(user_id, db=db):
                raise HTTPException(
                    status_code=403,
                    detail="Not authorized. Only team leads can create exams."
                )
        elif role != "teacher":
            raise HTTPException(status_code=403, detail="Not authorized.")

        exam_result = await db.execute(
            select(Exam.teacher_id).where(Exam.id == exam_id)
        )
        exam_teacher_id = exam_result.scalar_one_or_none()

        if not exam_teacher_id:
            raise HTTPException(status_code=404, detail="Exam not found.")

        if exam_teacher_id != user_id:
            raise HTTPException(
                status_code=403,
                detail="You are not authorized to modify this exam."
            )

        attempt_result = await db.execute(
            select(ExamAttempt.id)
            .where(
                and_(
                    ExamAttempt.exam_id == exam_id,
                    ExamAttempt.student_id == student_id
                )
            )
        )
        attempt_id = attempt_result.scalar_one_or_none()

        if not attempt_id:
            return JSONResponse(
                content={"message": "No exam attempt found for this student."}
            )

        await db.execute(
            delete(ExamResponse).where(ExamResponse.exam_attempt_id == attempt_id)
        )

        await db.execute(
            delete(ExamAttempt).where(ExamAttempt.id == attempt_id)
        )

        await db.commit()

        return JSONResponse(
            content={"message": "Exam status reset successfully."}
        )






    @app.post("/teacher/toggle_team_lead")
    async def toggle_team_lead(
        request: Request,
        student_id: int = Form(...),
        db: AsyncSession = Depends(get_db)
    ):
        require_teacher(request)

        result = await db.execute(
            select(User.is_team_lead)
            .where(User.id == student_id, User.role == "student")
        )

        try:
            current_status = result.scalar_one()
        except NoResultFound:
            raise HTTPException(status_code=404, detail="Student not found")

        new_status = 0 if current_status == 1 else 1

        # Update atomically
        update_result = await db.execute(
            update(User)
            .where(User.id == student_id)
            .values(is_team_lead=new_status)
            .returning(User.id)
        )

        if update_result.scalar_one_or_none() is None:
            raise HTTPException(status_code=404, detail="Failed to update team lead status")

        await db.commit()

        return RedirectResponse(url="/teacher/home", status_code=303)




