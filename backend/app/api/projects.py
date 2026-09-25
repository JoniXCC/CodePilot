from fastapi import APIRouter, Depends

from app.api.deps import get_settings_dep
from app.config import Settings
from app.schemas.projects import ProjectInfo
from app.services.projects import describe_project, list_projects, open_project

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("", response_model=list[ProjectInfo])
def get_projects(settings: Settings = Depends(get_settings_dep)) -> list[ProjectInfo]:
    return list_projects(settings.projects_dir)


@router.get("/{name}", response_model=ProjectInfo)
def get_project(name: str, settings: Settings = Depends(get_settings_dep)) -> ProjectInfo:
    return describe_project(open_project(settings.projects_dir, name))
