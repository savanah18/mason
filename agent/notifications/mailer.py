import smtplib
import markdown2
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os

# --- Configuration ---
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 465
SENDER_EMAIL = "aglubagerry@gmail.com"
APP_PASSWORD = os.getenv("EMAIL_APP_PASSWORD")  # Use an app password for Gmail

def send_notification(recipient_email, subject, body):
    # Create the email container
    msg = MIMEMultipart()
    msg['From'] = SENDER_EMAIL
    msg['To'] = recipient_email
    msg['Subject'] = subject

    # Attach the body text
    html_body = markdown2.markdown(body)
    msg.attach(MIMEText(html_body, 'html'))

    try:
        # Connect and send
        with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT) as server:
            server.login(SENDER_EMAIL, APP_PASSWORD)
            server.send_message(msg)
        print(f"✅ Notification sent to {recipient_email}")
    except Exception as e:
        print(f"❌ Error: {e}")

# --- Example Usage ---
if __name__ == "__main__":
    send_notification(
        recipient_email="aglubagerry@gmail.com",
        subject="[AUTOMATED NOTIFICATION] Your Python script has completed",
        body="""
### Summary Report for Workflow ID: **HONEST-ddbe3ece-3d65-49f7-8771-5dfcb983c306**

---

#### **Event Overview**
- **Package Name**: `media-api`
- **Version**: `22.6.10`
- **Registry**: `oci://registry-1.docker.io/bitnamicharts/nginx`
- **Environment**: `namespace media`
- **Action Type**: Fresh Install (due to absence of prior deployment)
- **Workflow ID**: `ddbe3ece-3d65-49f7-8771-5dfcb983c306`

---

#### **Pre-Check Phase**
1. **Helm Template Validation**  
- Successfully rendered the Helm chart templates for `nginx:v22.6.10`.  
- No syntax or structural errors were detected. All required resources (e.g., Deployments, Services, NetworkPolicies) are present and properly defined.  

2. **Existing Deployment Check**  
- Executed `helm-list-releases` in the `media` namespace.  
- Result: No existing release named `media-api` was found (`count = 0`).  
- Conclusion: A fresh installation is required.

---

#### **Installation & Upgrade Phase**
1. **Namespace Creation**  
- Detected missing namespace `media`.  
- Created the namespace via `kubernetes-resources_create_or_update`.  
- Status: Namespace `media` is now active and ready for use.

2. **Deployment Execution**  
- Initiated `helm-upgrade` with `--install` flag to create a new release.  
- Success: The release `media-api` was successfully installed in the `media` namespace.  
- Final Status:  
    - **Status**: `deployed`  
    - **Revision**: `1`  
    - **Last Deployed**: `Sat Apr 25 10:32:09 2026`  

---

#### **Post-Installation Checks**
- Verified deployment status via Helm. The application is fully deployed and operational.
- Key observations from the Helm notes:
- **Access from Cluster**: `media-api-nginx.media.svc.cluster.local` (port 80).
- **External Access**: Instructions provided to obtain the load balancer IP and service port for external access.
- **Warnings**:
    - Rolling tags (`latest`) detected in multiple containers (e.g., `bitnami/nginx`, `bitnami/git`, `bitnami/nginx-exporter`).  
    > *Recommendation*: Avoid rolling tags in production environments; use fixed versions for stability and security.
    - Missing resource definitions (e.g., CPU/Memory limits).  
    > *Recommendation*: Define explicit `resources` and `resourcesPreset` in the configuration for production readiness.

---

#### **Cleanup / Rollback**
- No rollback or cleanup actions were required. The installation succeeded and the deployment is stable.

---

#### **Final Outcome**
✅ **Success**: Package `media-api` has been successfully installed in the `media` namespace.  
🔍 **Observations**: Warnings about rolling tags and missing resource configurations require attention in future deployments.  
📌 **Next Steps**:  
- Address rolling tag usage by specifying fixed image versions.  
- Configure CPU and memory limits in the Helm values to meet production requirements.

---

#### **Introspection**
- The workflow followed a safe and robust sequence: validation → pre-check → installation → post-check.  
- Initial failure due to missing namespace was efficiently handled by creating the namespace before proceeding.  
- Tool selection was optimal: `helm-template` ensured chart integrity, `helm-list-releases` confirmed absence of duplicates, and `kubernetes-resources_create_or_update` enabled namespace provisioning.  
- Future improvements could include automated value customization based on environment-specific profiles.

This deployment is now live and functional under the given constraints.
        """
    )