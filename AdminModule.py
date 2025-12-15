from datetime import datetime
from zoneinfo import ZoneInfo
from fastapi.responses import HTMLResponse,JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import delete, insert, or_, select, and_, func, not_
from typing import List, Optional, Dict, Any
from fastapi import BackgroundTasks, Form, Path, Query, Request, HTTPException, Depends
from datetime import datetime
from typing import List, Dict, Any
from sqlalchemy import select, update, and_
from sqlalchemy.orm import selectinload, joinedload
from sqlalchemy.exc import NoResultFound
from Database import *


templates = Jinja2Templates(directory="templates")

def require_login(request: Request):
    if not request.session.get("user_id"):
        raise HTTPException(status_code=401, detail="Please log in to access this page.")

def init(app):
    @app.get("/admin/home", response_class=HTMLResponse)
    async def admin_home(
        request: Request,
        db: AsyncSession = Depends(get_db)
    ):

        total_users_result = await db.execute(select(func.count(User.id)))
        total_users = total_users_result.scalar_one()

        pending_result = await db.execute(
            select(func.count(User.id)).where(User.approved == 0)
        )
        pending_approvals = pending_result.scalar_one()

        total_exams_result = await db.execute(
            select(func.count(Exam.id))
        )
        total_exams = total_exams_result.scalar_one()

        approved_result = await db.execute(
            select(func.count(User.id)).where(User.approved == 1)
        )
        approved_users = approved_result.scalar_one()

        completion_rate = (
            (approved_users / total_users * 100) if total_users > 0 else 0
        )

        return templates.TemplateResponse("admin_home.html", {
            "request": request,
            "total_users": total_users,
            "pending_approvals": pending_approvals,
            "total_exams": total_exams,
            "completion_rate": f"{completion_rate:.2f}%",
        })


    @app.get("/admin/approvals", response_class=HTMLResponse)
    async def admin_approvals_page(
        request: Request,
        db: AsyncSession = Depends(get_db),
        role: Optional[str] = Query(None),
        department_id: Optional[int] = Query(None),
        search: Optional[str] = Query(None),
    ):

        # Base query: only unapproved users
        stmt = (
            select(User)
            .where(User.approved == 0)
            .order_by(User.created_at.desc())
        )

        # Filter by role
        if role in ("teacher", "student", "admin"):
            stmt = stmt.where(User.role == role)

        # Department filter — only meaningful for students
        if role == "student" and department_id is not None:
            stmt = stmt.where(User.department_id == department_id)

        # Search: username OR email (case-insensitive)
        if search:
            search_term = f"%{search.strip().lower()}%"
            stmt = stmt.where(
                or_(
                    func.lower(User.username).ilike(search_term),
                    func.lower(User.email).ilike(search_term)
                )
            )

        # Execute query with department preload (for display)
        result = await db.execute(
            stmt.options(selectinload(User.department))
        )
        users = result.scalars().all()

        # Prepare clean list for template
        users_data = []
        for user in users:
            users_data.append({
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "role": user.role,
                "department_id": user.department_id,
                "department_name": user.department.name if user.department else None,
                "approved": user.approved,
            })

        # Fetch departments only if we're filtering/showing students
        departments = []
        if role == "student" or role is None:  # show dropdown if student tab or no filter
            dept_result = await db.execute(
                select(Department).order_by(Department.name)
            )
            departments = [{"id": d.id, "name": d.name} for d in dept_result.scalars().all()]

        return templates.TemplateResponse("admin_approvals.html", {
            "request": request,
            "users": users_data,
            "departments": departments,
            "selected_role": role,
            "selected_department": department_id,
            "search": search or "",
        })



    @app.post("/admin/approvals/approve/{user_id}", response_class=RedirectResponse)
    async def admin_approve_user(
        request: Request,
        user_id: int,
        db: AsyncSession = Depends(get_db)
    ):


        result = await db.execute(
            update(User)
            .where(User.id == user_id)
            .values(approved=1)
        )

        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="User not found or already approved")

        await db.commit()

        return RedirectResponse(url="/admin/approvals", status_code=302)


    @app.get("/admin/exams", response_class=HTMLResponse)
    async def admin_exams_page(
        request: Request,
        db: AsyncSession = Depends(get_db),
        department: Optional[str] = Query(None),   
        search: Optional[str] = Query(None)       
    ):
        
        # Normalize department input
        department_id: Optional[int] = None
        if department:
            if department.isdigit():
                department_id = int(department)
            # Optionally support department name lookup (bonus feature)
            elif isinstance(department, str) and len(department.strip()) > 0:
                dept_result = await db.execute(
                    select(Department.id).where(Department.name.ilike(department.strip()))
                )
                found_id = dept_result.scalars().first()
                if found_id:
                    department_id = found_id

        # Build base query with necessary joins for display
        query = (
            select(Exam)
            .add_columns(
                Department.name.label("department_name"),
                User.username.label("teacher_name")
            )
            .join(Department, Department.id == Exam.department_id, isouter=True)
            .join(User, User.id == Exam.teacher_id)
            .order_by(Exam.created_at.desc())
        )

        # Apply filters
        if department_id is not None:
            query = query.where(Exam.department_id == department_id)

        if search and search.strip():
            search_term = f"%{search.strip()}%"
            query = query.where(
                or_(
                    Exam.name.ilike(search_term),
                    Exam.subject.ilike(search_term)
                )
            )

        # Execute
        result = await db.execute(query)
        exams = result.all()

        exams_data = []
        for exam, dept_name, teacher_name in exams:
            exams_data.append({
                "id": exam.id,
                "name": exam.name,
                "subject": exam.subject,
                "start_time": exam.start_time,
                "end_time": exam.end_time,
                "duration": exam.duration,
                "department_id": dept_name or "No Department",
                "teacher": teacher_name or "Unknown",
                "created_at": exam.created_at,
            })

        dept_result = await db.execute(select(Department.id, Department.name).order_by(Department.name))
        departments = [{"id": d.id, "name": d.name} for d in dept_result.all()]

        return templates.TemplateResponse("admin_exams.html", {
            "request": request,
            "exams": exams_data,
            "departments": departments,
            "selected_department": department_id or department,  # preserve input
            "search": search,
        })


    @app.post("/admin/exams/delete/{exam_id}", response_class=RedirectResponse)
    async def admin_delete_exam(
        request: Request,
        exam_id: int,
        db: AsyncSession = Depends(get_db)
    ):


        async with db.begin():  # Full transaction safety
            try:
                # 1. Delete all Options (via Question → Option cascade or explicit)
                await db.execute(
                    delete(Option).where(
                        Option.question_id.in_(
                            select(Question.id).where(Question.exam_id == exam_id)
                        )
                    )
                )

                # 2. Delete all Questions
                await db.execute(
                    delete(Question).where(Question.exam_id == exam_id)
                )

                # 3. Delete the Exam itself
                result = await db.execute(
                    delete(Exam).where(Exam.id == exam_id).returning(Exam.id)
                )

                if result.scalar_one_or_none() is None:
                    raise HTTPException(status_code=404, detail="Exam not found or already deleted")

            except Exception as e:
                await db.rollback()
                raise HTTPException(status_code=500, detail=f"Failed to delete exam: {str(e)}")

        return RedirectResponse(url="/admin/exams", status_code=302)


    @app.post("/admin/block/{user_id}")
    async def admin_block_user(
        request: Request,
        user_id: int,
        db: AsyncSession = Depends(get_db)
    ):

        result = await db.execute(
            update(User)
            .where(User.id == user_id)
            .values(approved=-1)
            .returning(User.id)
        )

        if result.scalar_one_or_none() is None:
            raise HTTPException(status_code=404, detail="User not found")

        await db.commit()
        return RedirectResponse(url="/admin/users", status_code=302)


    @app.get("/admin/users", response_class=HTMLResponse)
    async def admin_users_page(
        request: Request,
        db: AsyncSession = Depends(get_db),
        department: Optional[int] = None,
        role: Optional[str] = None,
        search: Optional[str] = None
    ):


        # Base query
        stmt = (
            select(
                User.id,
                User.username,
                User.email,
                User.role,
                User.approved,
                User.department_id,
                Department.name.label("department_name")
            )
            .outerjoin(Department, Department.id == User.department_id)
        )

        # Filters
        if department is not None:
            stmt = stmt.where(User.department_id == department)
        if role:
            stmt = stmt.where(User.role == role)
        if search:
            stmt = stmt.where(User.username.ilike(f"%{search}%"))

        stmt = stmt.order_by(User.username)

        result = await db.execute(stmt)
        users = result.all()

        # Convert to list of dicts for template (same structure as before)
        users_list = [
            {
                "id": u.id,
                "username": u.username,
                "email": u.email,
                "role": u.role,
                "approved": u.approved,
                "department_id": u.department_id,
                "department_name": u.department_name or "N/A",
            }
            for u in users
        ]

        # Fetch all departments for dropdown
        depts_result = await db.execute(select(Department.id, Department.name).order_by(Department.name))
        departments = depts_result.all()

        return templates.TemplateResponse("admin_users.html", {
            "request": request,
            "users": users_list,
            "departments": departments,
            "selected_department": department,
            "role": role,
            "search": search,
        })

    @app.get("/feedback/admin/", response_class=HTMLResponse)
    async def admin_feedback_page(request: Request):
        if request.session.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Admin access required")

        return templates.TemplateResponse("admin_feedback.html", {"request": request})
