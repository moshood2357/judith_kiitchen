def password_reset_email(reset_link):
    return f"""
    <div style="font-family:Arial; max-width:500px;">
        <h2 style="color:#0f172a;">Reset Your Password</h2>

        <p>You requested a password reset. Click below:</p>

        <a href="{reset_link}" style="
            display:inline-block;
            padding:12px 18px;
            background:#22c55e;
            color:#fff;
            text-decoration:none;
            border-radius:8px;
            font-weight:600;
        ">
            Reset Password
        </a>

        <p style="margin-top:20px; font-size:12px; color:#64748b;">
            If you didn’t request this, ignore this email.
        </p>
    </div>
    """