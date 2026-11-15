MASTER PROJECT PROMPT — CAMPUS RETAIN 3.0
Act as a world-class SaaS architect, senior full-stack engineer, cybersecurity specialist, UI/UX designer, database architect, AI engineer and product strategist.
Your task is to transform my existing project, Campus Retain 2.0, into a premium, production-ready, multi-college lost-and-found SaaS platform called:
CAMPUS RETAIN 3.0
One Platform. Multiple Colleges. One Connected Campus Community.
This is an existing, partially developed and deployed project. You MUST inspect the entire existing repository before making changes.
Do not blindly replace existing code. Understand the current architecture, identify reusable components, preserve working functionality and progressively upgrade the application.
1. PRODUCT VISION
Campus Retain should become a centralized lost-and-found platform serving multiple colleges across Bengaluru, Karnataka, India.
Initial target institutions:

* Alliance University
* MVJ College of Engineering
* BMS College of Engineering
* PES University
* Dayananda Sagar College of Engineering

These are prospective institutions, not confirmed partners.
The platform must support adding unlimited colleges without creating separate applications or databases for each college.
Each institution must have its own isolated environment, branding, students, administrators, items, claims and analytics.
The platform should eventually be commercially viable as a subscription-based SaaS product.
2. FIRST: AUDIT THE EXISTING PROJECT
Before coding:

1. Inspect every directory and file.
2. Read the existing app.py, templates, static assets, requirements.txt, vercel.json and database configuration.
3. Understand every existing route, database model and frontend interaction.
4. Identify security vulnerabilities, architectural limitations and broken functionality.
5. Identify existing environment variables and integrations.
6. Inspect the existing PostgreSQL database schema and migration requirements.
7. Prepare a concise implementation plan.
8. Preserve all working functionality unless there is a clear reason to improve it.

Do not delete existing functionality without replacing it with an equivalent or better implementation.
Do not introduce dummy data into production.
3. TECHNOLOGY STACK
Use a maintainable architecture.
Backend:

* Python
* Flask
* Flask Blueprints
* Flask-SQLAlchemy
* Flask-Migrate
* PostgreSQL (Neon)
* Flask-Limiter
* Flask-WTF / CSRF protection
* Secure password hashing
* Proper session management

Frontend:

* React
* TypeScript
* Vite
* Tailwind CSS
* Framer Motion
* Lucide icons
* Responsive design

Infrastructure:

* Vercel-compatible deployment or a suitable alternative if required by the architecture
* Neon PostgreSQL
* Cloud object storage for images
* Gmail SMTP
* Optional Twilio SMS
* Environment-based configuration

AI:

* Image similarity matching
* Smart search
* Automatic item description assistance
* Duplicate report detection

Do not add unnecessary dependencies. Verify compatibility before installation.
If migrating from the existing HTML frontend to React, do it incrementally while keeping the existing production application functional.
4. MULTI-TENANT ARCHITECTURE
This is the most important architectural requirement.
Build a secure multi-tenant architecture.
Database entities should include:

* College
* Campus
* Department
* User
* Role
* Permission
* Item
* ItemImage
* Claim
* Notification
* CollectionPoint
* Event
* AuditLog
* Subscription
* PlatformSettings

Every college-owned record must have the appropriate college_id and, where applicable, campus_id.
Requirements:

* College-specific registration.
* College-specific login and authentication.
* College-specific dashboards.
* College-specific item listings.
* College-specific administrators.
* College-specific analytics.
* College-specific email configuration.
* College-specific branding.
* College-specific collection locations.
* Configurable college email domains.
* Strict tenant isolation.

Implement server-side authorization on every relevant endpoint.
Consider PostgreSQL Row-Level Security as an additional security layer.
Never trust college_id supplied by the browser without validating the authenticated user's permissions.
A student from Alliance University must never access another college's private data simply by changing a URL or API parameter.
5. USER ROLES AND PERMISSIONS
Create the following roles:

1. Platform Super Admin
2. College Admin
3. Campus Moderator
4. Security Staff
5. Student

Platform Super Admin:

* Manage all colleges.
* Approve college registrations.
* Manage college administrators.
* View platform-wide analytics.
* Manage subscriptions.
* Configure platform settings.
* Suspend institutions when necessary.

College Admin:

* Manage students within their institution.
* Manage found-item reports.
* Verify and process claims.
* Manage campus moderators.
* View analytics.
* Export reports.
* Configure collection points.

Campus Moderator:

* Manage assigned campus listings.
* Review reports and claims.
* Escalate suspicious cases.

Security Staff:

* Verify collection OTPs.
* Confirm physical item handovers.
* Update collection records.

Student:

* Report found items.
* Report lost items.
* Search for items.
* Submit claims.
* Track claims.
* Receive notifications.

Implement proper permission checks rather than relying on frontend role restrictions.
6. AUTHENTICATION AND SECURITY
Security must be a priority.
Implement:

* Verified college email registration.
* Secure password hashing.
* Password reset using securely stored, hashed, short-lived OTPs.
* OTP rate limiting.
* Login attempt protection.
* Session expiration.
* Secure, HTTP-only cookies.
* SameSite cookie configuration.
* CSRF protection.
* XSS prevention.
* SQL injection protection.
* Input validation.
* File upload validation.
* File size restrictions.
* Secure image storage.
* Authorization checks on every protected endpoint.
* Audit logging.
* Security headers.
* Rate limiting.
* Safe error handling.

Remove:

* Public database initialization endpoints.
* Public testing endpoints.
* Hardcoded secrets.
* Fallback production secret keys.
* Plain-text password comparisons.
* Trust in user-supplied identity information.

Never expose secret details, private claimant information or sensitive item information to unauthorized users.
Use secure configuration and fail safely when required production secrets are missing.
7. LOST-AND-FOUND CORE SYSTEM
Improve the existing lost-and-found workflow.
Found-item reporting:

* Item name.
* Category.
* Description.
* Date found.
* Approximate location.
* Campus.
* Multiple photographs.
* Optional identifying details kept private.
* Contact and reporting details.

Lost-item reporting:

* Item name.
* Category.
* Description.
* Date lost.
* Approximate location.
* Photographs, if available.
* Distinguishing characteristics.

Claim workflow:

1. Student finds a potentially matching item.
2. Student submits a claim.
3. Student provides ownership evidence.
4. Admin reviews the claim.
5. Admin approves or rejects the claim.
6. Approved students receive a secure pickup notification.
7. Security staff verifies the pickup OTP.
8. Item is marked as successfully returned.

Important rules:

* Prevent multiple conflicting active claims.
* Preserve complete claim history.
* Never overwrite earlier claim records.
* Require admin verification.
* Maintain a complete audit trail.
* Do not reveal secret identifying details to claimants.
* Do not expose personal contact information unnecessarily.

8. AI-POWERED FEATURES
Build AI capabilities progressively.
A. AI Image Matching
When an item is reported lost or found, compare image embeddings to identify visually similar items.
B. Smart Search
Allow students to search naturally:
"Black wallet lost near the library yesterday."
C. AI Description Generator
Generate a suggested description from an uploaded photograph.
D. Duplicate Detection
Identify potentially duplicated reports.
E. Smart Recommendations
Show potentially matching items to students.
F. Fraud Detection
Flag suspicious claim patterns for human review.
Important:
AI recommendations must never automatically approve ownership claims.
Use genuine algorithms and real integrations. Never pretend an AI feature works when it is only a static interface.
If external AI services require API keys, build a proper integration interface and document the configuration.
9. INTER-COLLEGE NETWORK
Create an optional inter-college matching network.
Example:
An Alliance University student loses a laptop bag during an event at MVJ College.
The system should be able to identify a possible match reported at MVJ, provided both institutions have enabled inter-college matching.
Features:

* Opt-in inter-college discovery.
* Permission-controlled item sharing.
* Cross-college matching.
* Notifications about potential matches.
* Secure inter-college handover.
* Audit logs for cross-college access.

Keep college data private by default.
Never share secret item details or personal information through public cross-college listings.
10. ADVANCED FEATURES
Implement these features as separate modules:
A. Event Mode

* Temporary lost-and-found portals for college fests.
* Hackathons.
* Sports events.
* Cultural events.
* Configurable event administrators.

B. QR Item Identification

* Generate unique QR codes.
* Allow security staff to scan and identify registered items.
* Do not expose sensitive information through public QR codes.

C. Campus Lost-and-Found Map

* Display approximate locations.
* Filter by campus and category.
* Avoid revealing sensitive pickup locations.

D. Digital Recovery Wallet

* Show a student's reported items.
* Display claim history.
* Display successfully recovered items.

E. Notifications

* Email.
* Optional SMS.
* Browser push notifications.
* Claim status updates.
* Pickup reminders.
* Potential match alerts.

F. Collection Management

* Multiple collection points.
* Pickup scheduling.
* OTP-based verification.
* Staff handover records.

11. STUDENT DASHBOARD
Create a premium student dashboard.
Include:

* Welcome section.
* College and campus identification.
* Search bar.
* Recently found items.
* Recently reported lost items.
* Recommended matches.
* My reports.
* My claims.
* Saved items.
* Notification centre.
* Profile settings.
* Help and support.

The dashboard must be simple enough for a first-time user.
Use intuitive navigation and clear actions.
12. COLLEGE ADMIN DASHBOARD
Create a professional administration dashboard.
Include:

* Total items reported.
* Successfully recovered items.
* Pending claims.
* Rejected claims.
* Active students.
* Recovery rate.
* Average recovery time.
* Monthly statistics.
* Category distribution.
* Campus-wise statistics.
* Recent activities.
* Suspicious activity alerts.

Provide:

* Search and filtering.
* Pagination.
* Excel and PDF export.
* Date-range filtering.
* Admin activity logs.
* Multiple administrator support.

Do not display fabricated statistics.
13. PLATFORM SUPER ADMIN DASHBOARD
Create a separate platform-level dashboard.
Features:

* Total registered colleges.
* Active institutions.
* Total students.
* Total reported items.
* Total recovered items.
* Platform-wide usage.
* College onboarding requests.
* College verification.
* Subscription management.
* Storage monitoring.
* Platform health.
* Security events.
* Audit history.

Only authorized platform administrators can access this dashboard.
14. UI/UX DESIGN REQUIREMENTS
The design must look like a premium, professionally funded SaaS product.
Design inspiration:

* Linear
* Stripe
* Vercel
* Notion
* Modern enterprise SaaS dashboards.

Visual requirements:

* Clean typography.
* Excellent spacing.
* Consistent design system.
* Elegant navigation.
* Professional cards.
* Beautiful empty states.
* Smooth transitions.
* Subtle animations.
* Attractive charts.
* Responsive layouts.
* Accessible colour contrast.
* Loading skeletons.
* Helpful error states.
* Confirmation dialogs.
* Toast notifications.

Provide:

* Light mode.
* Dark mode.
* Mobile-responsive interface.
* Tablet-responsive interface.
* Desktop dashboard.

Avoid:

* Excessive gradients.
* Unnecessary animations.
* Overloaded dashboards.
* Excessive rounded cards.
* Random icons.
* Fake notifications.
* Fake statistics.
* Generic template appearance.

Create a consistent visual identity for Campus Retain.
The interface should feel like a real commercial SaaS platform.
15. DATABASE AND STORAGE
Use PostgreSQL through Neon.
Requirements:

* Proper relational database design.
* Foreign key constraints.
* Unique constraints.
* Database indexes.
* Migration support.
* Transaction safety.
* Pagination.
* Query optimization.
* Connection pooling.
* Backup and recovery strategy.

Do not store large photographs as Base64 strings in PostgreSQL.
Use external object storage and save image URLs and metadata in the database.
Implement:

* Image compression.
* Image format validation.
* Upload limits.
* Secure access to private images.
* Cleanup of unused images.

Never store uploaded files in temporary serverless filesystem paths as permanent storage.
16. PERFORMANCE AND SCALABILITY
Optimize for growth from one college to dozens of colleges.
Requirements:

* Efficient database queries.
* Avoid N+1 queries.
* Pagination.
* Lazy loading.
* Image optimization.
* Caching where appropriate.
* Background processing for expensive operations.
* Efficient notification delivery.
* API response consistency.
* Monitoring and error logging.

Do not claim unlimited scalability without testing.
Document infrastructure requirements and scaling limitations.
17. TESTING
Implement real tests.
Test:

* Registration.
* Email verification.
* Login.
* Password recovery.
* Role-based permissions.
* College data isolation.
* Item reporting.
* Claim submission.
* Multiple claim prevention.
* Approval and rejection.
* OTP collection.
* Image uploads.
* Notifications.
* Admin operations.
* Cross-college matching.
* API validation.
* CSRF protection.
* Rate limiting.

Include integration tests and security-focused tests.
Do not mark a feature as completed without testing it.
18. DEPLOYMENT
Prepare production deployment.
Provide:

* Updated requirements.txt.
* Environment variable documentation.
* Database migration instructions.
* Production configuration.
* Vercel compatibility assessment.
* Alternative hosting recommendations if necessary.
* Storage configuration.
* SMTP configuration.
* Deployment instructions.
* Health-check endpoint.
* Error monitoring.

Never commit secrets, API keys, passwords or database credentials.
Do not run destructive migrations against production without explicit approval and a backup.
19. DEVELOPMENT RULES
Follow these instructions strictly:

1. Do not create dummy data.
2. Do not hardcode college-specific assumptions.
3. Do not create fake AI functionality.
4. Do not leave buttons without working actions.
5. Do not leave unfinished pages.
6. Do not remove existing features without replacement.
7. Do not compromise security for convenience.
8. Do not duplicate code unnecessarily.
9. Do not expose sensitive information.
10. Do not assume a third-party API is available without verifying it.
11. Use environment variables for secrets.
12. Keep the code modular and maintainable.
13. Write clear documentation.
14. Test every important feature.
15. Do not claim deployment succeeded unless verified.

Work in small, logical phases.
After each phase:

* Explain what was implemented.
* List modified files.
* List database migrations.
* Run relevant tests.
* Report errors.
* Explain anything requiring manual configuration.

Do not stop after generating a plan. Start implementing the first phase after the audit.
If an operation requires my credentials, account access, paid subscription or approval, explain exactly what is needed rather than fabricating success.
20. FINAL EXPECTATION
The final product must be a real, secure, functional, multi-tenant SaaS platform.
Campus Retain should be capable of onboarding different colleges, managing their students, processing lost-and-found claims, providing intelligent matching, and giving institutions meaningful analytics.
Build it as a product that I can confidently demonstrate to college management, potential institutional partners, investors and actual students.
The priority is not to create the largest number of features. The priority is to create a secure, polished, reliable product where every implemented feature actually works.
Start by auditing the existing repository. Then provide the implementation roadmap and begin Phase 1.
