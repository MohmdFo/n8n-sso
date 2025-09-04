"""
Cookie setting endpoint for n8n authentication.
This endpoint should be deployed on the same domain as n8n or accessible via proxy.
"""
from fastapi import APIRouter, Query
from fastapi.responses import RedirectResponse, HTMLResponse
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/n8n-auth", tags=["N8N Auth Helper"])

@router.get("/set-cookie")
def set_n8n_cookie(
    token: str = Query(..., description="n8n authentication token"),
    redirect_url: str = Query(default="/home/workflows", description="URL to redirect to after setting cookie")
):
    """
    Set n8n authentication cookie and redirect.
    This endpoint should be accessible from n8n's domain or via proxy.
    """
    logger.info(f"Setting n8n-auth cookie and redirecting to {redirect_url}")
    
    response = RedirectResponse(url=redirect_url, status_code=302)
    
    # Set the n8n authentication cookie
    response.set_cookie(
        key="n8n-auth",
        value=token,
        path="/",
        httponly=True,
        secure=False,  # Set to True in production with HTTPS
        samesite="lax",
        max_age=7 * 24 * 3600  # 7 days
    )
    
    return response

@router.get("/bridge")  
def auth_bridge(
    token: str = Query(..., description="n8n authentication token"),
    redirect_url: str = Query(default="/home/workflows", description="URL to redirect to")
):
    """
    JavaScript bridge for cross-domain cookie setting.
    Returns HTML that will set cookie and redirect.
    """
    
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Authentication Bridge</title>
        <meta charset="utf-8">
    </head>
    <body>
        <div style="text-align: center; padding: 50px; font-family: Arial, sans-serif;">
            <h2>🔐 Completing authentication...</h2>
            <p>Setting up your session...</p>
            <div style="margin: 20px;">
                <div style="border: 3px solid #f3f3f3; border-top: 3px solid #3498db; border-radius: 50%; width: 40px; height: 40px; animation: spin 1s linear infinite; margin: 0 auto;"></div>
            </div>
        </div>
        
        <script>
            // Set the authentication cookie
            document.cookie = 'n8n-auth={token}; path=/; max-age=604800; SameSite=Lax';
            
            // Redirect after setting cookie
            setTimeout(function() {{
                window.location.href = '{redirect_url}';
            }}, 1000);
        </script>
        
        <style>
            @keyframes spin {{
                0% {{ transform: rotate(0deg); }}
                100% {{ transform: rotate(360deg); }}
            }}
        </style>
    </body>
    </html>
    """
    
    return HTMLResponse(content=html_content, status_code=200)
