"""Manually annotated synthetic extracts. Mapping None means no expected catalog identity."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Fixture:
    id: str
    text: str
    skills: dict[str, str | None]
    sections: tuple[str, ...]
    entities: tuple[tuple[str, str], ...] = ()


FIXTURES = (
    Fixture('it-01-library', """EDUCATION
Bachelor of Computer Science, Universiti Reka, 2025
Academic Projects
Library Tool: Borrowing records
Developed a search application using Python, Django, PostgreSQL and Git.""",
            {'Python': None, 'Django': None, 'PostgreSQL': 'PostgreSQL', 'Git': None},
            ('education', 'projects'), (('education', 'Bachelor of Computer Science'), ('project', 'Library Tool'))),
    Fixture('it-02-portal', """Kemahiran Teknikal: JS, Postgres, CSS
Pendidikan: Diploma in Information Technology, Politeknik Murni, 2024
Projek Tahun Akhir: Booking Portal
Description: Campus room reservations""",
            {'JS': 'JavaScript', 'Postgres': 'PostgreSQL', 'CSS': 'CSS'},
            ('skills', 'education', 'projects'), (('education', 'Diploma in Information Technology'), ('project', 'Booking Portal'))),
    Fixture('it-03-data', """Work Experience
Data Intern at Blue Atlas Sdn. Bhd. | Jun 2024 – Aug 2024
Used SQL and statistics.
Technical Skills: SQL, MATLAB, Python""",
            {'SQL': 'SQL', 'statistics': 'statistics', 'MATLAB': 'MATLAB', 'Python': None},
            ('experience', 'skills'), (('experience', 'Data Intern'),)),
    Fixture('it-04-web', """Professional Summary: Experienced in web programming.
Personal Projects: Community Site
Technologies: PHP, JavaScript, CSS
Role: Frontend contributor
https://example.test/community""",
            {'web programming': 'web programming', 'PHP': 'PHP', 'JavaScript': 'JavaScript', 'CSS': 'CSS'},
            ('summary', 'projects'), (('project', 'Community Site'),)),
    Fixture('it-05-networks', """Technical Skills
cyber security; SQL
CERTIFICATIONS
Campus networking workshop
Desired Role: Looking to learn PHP.""",
            {'cyber security': 'cyber security', 'SQL': 'SQL'}, ('skills', 'certifications', 'excluded')),
    Fixture('it-06-mobile', """Academic Projects
Habit Tracker: Local prototype
Tools: C#, SQLite
Diploma in Software Engineering, Kolej Reka""",
            {'C#': 'C#', 'SQLite': None}, ('projects',), (('project', 'Habit Tracker'),)),
    Fixture('it-07-support', """Latihan Industri
ICT Support Intern at Kertas Sdn. Bhd. | Julai 2025 hingga September 2025
Used Git.
Skills: customer service / PostgreSQL""",
            {'Git': None, 'customer service': 'customer service', 'PostgreSQL': 'PostgreSQL'},
            ('experience', 'skills'), (('experience', 'ICT Support Intern'),)),
    Fixture('it-08-systems', """SKILLS
Java (computer programming), C++, GitHub Actions
Education
Bachelor of Software Engineering, Universities Example, currently pursuing""",
            {'Java (computer programming)': 'Java (computer programming)', 'C++': 'C++', 'GitHub Actions': None},
            ('skills', 'education'), (('education', 'Bachelor of Software Engineering'),)),
    Fixture('it-09-robot', """Education: Foundation in Science, 2024
Academic Projects
Queue Simulator
Built a prototype using MATLAB.
Technical Skills: C++, MATLAB""",
            {'MATLAB': 'MATLAB', 'C++': 'C++'}, ('education', 'projects', 'skills'),
            (('education', 'Foundation in Science'), ('project', 'Queue Simulator'))),
    Fixture('it-10-malay', """Ringkasan: Membangunkan portal menggunakan PHP dan CSS.
Kemahiran: PHP • CSS • PostgreSQL
Pengalaman Kerja
Pembangun Sambilan di Taman Labs | Sep 2024 – kini""",
            {'PHP': 'PHP', 'CSS': 'CSS', 'PostgreSQL': 'PostgreSQL'},
            ('summary', 'skills', 'experience'), (('experience', 'Pembangun Sambilan'),)),
    Fixture('eng-01-cad', """Technical Skills: CAD software; technical drawings
Education
Diploma in Mechanical Engineering, Politeknik Reka, 2025
Final Year Project
Clamp Prototype
Designed a clamp using CAD software.""",
            {'CAD software': 'CAD software', 'technical drawings': 'technical drawings'},
            ('skills', 'education', 'projects'), (('education', 'Diploma in Mechanical Engineering'), ('project', 'Clamp Prototype'))),
    Fixture('eng-02-electrical', """Work Experience
Engineering Trainee at Atlas Lab | Jan 2025 - Apr 2025
Used MATLAB for test plots.
Skills: electrical engineering, MATLAB, LTspice""",
            {'electrical engineering': 'electrical engineering', 'MATLAB': 'MATLAB', 'LTspice': None},
            ('experience', 'skills'), (('experience', 'Engineering Trainee'),)),
    Fixture('eng-03-qa', """Industrial Training
Quality Technician | Reka Sdn. Bhd. | Feb 2024 to Jun 2024
Reviewed fixture readings.
Skills and Competencies: quality standards, statistics
Certifications: Safety induction""",
            {'quality standards': 'quality standards', 'statistics': 'statistics'},
            ('experience', 'skills', 'certifications'), (('experience', 'Quality Technician'),)),
    Fixture('eng-04-controls', """Pendidikan
Ijazah Sarjana Muda dalam Kejuruteraan Elektrik, Universiti Atlas
Projek Akademik
Motor Controller: Bench model
Technologies: MATLAB, C++, PLC""",
            {'MATLAB': 'MATLAB', 'C++': 'C++', 'PLC': None},
            ('education', 'projects'), (('education', 'Ijazah Sarjana Muda dalam Kejuruteraan Elektrik'), ('project', 'Motor Controller'))),
    Fixture('eng-05-production', """Professional Summary
Used CAD software.
Employment History
Contract Engineer at Merah Works | 2023 – 2024
Skills: mechanical engineering, project management""",
            {'CAD software': 'CAD software', 'mechanical engineering': 'mechanical engineering',
             'project management': 'project management'},
            ('summary', 'experience', 'skills'), (('experience', 'Contract Engineer'),)),
    Fixture('biz-01-accounts', """Skills: accounting, financial statements
Education: Diploma in Accounting, Kolej Atlas, 2023
Employment History
Part-time Accounts Assistant at Campus Shop | 2024 – Present""",
            {'accounting': 'accounting', 'financial statements': 'financial statements'},
            ('skills', 'education', 'experience'), (('education', 'Diploma in Accounting'), ('experience', 'Part-time Accounts Assistant'))),
    Fixture('biz-02-finance', """Professional Summary: Experienced in financial analysis.
Internship Experience
Finance Intern | Taman Finance | Jan 2025 – Mac 2025
Technical Skills: Microsoft Excel, statistics""",
            {'financial analysis': 'financial analysis', 'Microsoft Excel': None, 'statistics': 'statistics'},
            ('summary', 'experience', 'skills'), (('experience', 'Finance Intern'),)),
    Fixture('biz-03-marketing', """Academic Projects: Campus Survey
Technologies: SQL
Conducted market research for the campus survey.
Skills: market research, social media management""",
            {'SQL': 'SQL', 'market research': 'market research', 'social media management': 'social media management'},
            ('projects', 'skills'), (('project', 'Campus Survey'),)),
    Fixture('biz-04-tax', """Pendidikan: Bachelor of Business, Universiti Murni, expected 2027
Soft Skills
customer service, Teamwork
Skills: tax legislation
Work Experience: Retail Assistant at Atlas Store""",
            {'customer service': 'customer service', 'Teamwork': None, 'tax legislation': 'tax legislation'},
            ('education', 'skills', 'experience'), (('education', 'Bachelor of Business'), ('experience', 'Retail Assistant'))),
    Fixture('biz-05-events', """Personal Projects
Campus Fair Budget: Tracked vendor expenses
Role: Budget coordinator
Technical Skills
project management | financial statements | budgeting""",
            {'project management': 'project management', 'financial statements': 'financial statements', 'budgeting': None},
            ('projects', 'skills'), (('project', 'Campus Fair Budget'),)),
    Fixture('mix-01-retail', """PENGALAMAN KERJA
Cashier at Buku Campus | 2025 – kini
Provided customer service to students.
Kemahiran Insaniah: customer service, communication principles""",
            {'customer service': 'customer service', 'communication principles': 'communication principles'},
            ('experience', 'skills'), (('experience', 'Cashier'),)),
    Fixture('mix-02-media', """Academic Qualifications: Diploma in Media, Kolej Murni
Projects
Interview Archive
Description: Volunteer interviews
Tools: digital image processing, Audacity
Certifications: Media workshop""",
            {'digital image processing': 'digital image processing', 'Audacity': None},
            ('education', 'projects', 'certifications'), (('education', 'Diploma in Media'), ('project', 'Interview Archive'))),
    Fixture('mix-03-tutoring', """Profile: Currently learning statistics.
Part-time Tutor at Atlas Centre
Pendidikan: STPM, Sekolah Reka, 2024
Skills: lesson planning, customer service""",
            {'lesson planning': None, 'customer service': 'customer service'},
            ('summary', 'education', 'skills'), (('education', 'STPM'), ('experience', 'Part-time Tutor'))),
    Fixture('mix-04-shop', """Work History
Shop Assistant at Taman Shop (Part-time)
- Managed customer service for walk-in customers.
Skills: customer service, stock counting""",
            {'customer service': 'customer service', 'stock counting': None},
            ('experience', 'skills'), (('experience', 'Shop Assistant'),)),
    Fixture('mix-05-arts', """Personal Projects
Campus Zine
Role: Layout contributor
Tools: InDesign, use word processing software
Academic Background
Bachelor of Design, Universiti Reka, 2025""",
            {'InDesign': None, 'use word processing software': 'use word processing software'},
            ('projects', 'education'), (('project', 'Campus Zine'), ('education', 'Bachelor of Design'))),
    Fixture('hard-01-negation', """Summary: No experience with PostgreSQL or JavaScript, but used SQL.
Skills: SQL, Not familiar with PHP
Objective: Seeking a role using MATLAB.""",
            {'SQL': 'SQL'}, ('summary', 'skills', 'excluded')),
    Fixture('hard-02-substrings', """Technical Skills: C++, Node.js, NoSQL, GitHub
Used digit counters and a postgresqlish parser.
https://example.test/SQL/PHP
Contact: mysql@example.test""",
            {'C++': 'C++', 'Node.js': None, 'NoSQL': 'NoSQL', 'GitHub': None}, ('skills', 'other')),
    Fixture('hard-03-uncertain', """I am interested in learning JavaScript.
Introductory coursework in statistics.
Experience with instrument handling.
Diploma in Information Technology, 2023
Education makes me curious.""",
            {'instrument handling': None}, (), (('education', 'Diploma in Information Technology'),)),
    Fixture('hard-04-hyphen', """# SKILLS: cyber-security, customer service, js
Projects
Study Board
Created a mockup.
Job Requirements: PostgreSQL and CSS""",
            {'cyber-security': None, 'customer service': 'customer service', 'js': None},
            ('skills', 'projects', 'excluded'), (('project', 'Study Board'),)),
    Fixture('hard-05-embedded', """Work Experience is often helpful for internships.
Professional Summary:
Used SQL; never used C++.
Technologies: WidgetLang, PHP
Reference: No résumé content below.""",
            {'SQL': 'SQL', 'WidgetLang': None, 'PHP': 'PHP'}, ('summary', 'excluded')),
)
