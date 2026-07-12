For public charter schools that are reported as dependent programs within a traditional public school district’s Local Education Agency (LEA) (Structure C), isolating their enrollment and staffing from the host district's totals is possible but is subject to major structural limitations and data quality caveats.

## **Method for Separating Charter Metrics from District Totals**

To isolate the traditional, district-run (non-charter) totals for enrollment and instructional staff within a mixed LEA, analysts employ a school-level subtraction protocol:

### **Student Enrollment**

Isolating traditional student enrollment is highly reliable. Analysts can subtract the sum of the student membership of all dependent charter schools (ccd\_sch\_052 / MEMBER via EDFacts file specification FS052) from the host district's overall LEA-level student membership count (ccd\_lea\_052 / MEMBER):

$$\\text{Traditional Enrollment} \= \\text{MEMBER}\_{\\text{LEA}} \- \\sum \\text{MEMBER}\_{\\text{Charter Schools}}$$  
This method is highly robust because student enrollment reporting is virtually 100% complete and vertically consistent between school-level and district-level files in the Common Core of Data (CCD).

### **Instructional Staff (Teachers)**

Isolating classroom teachers is also mathematically straightforward but less precise than enrollment. The sum of school-level charter teacher Full-Time Equivalents (FTEs) (ccd\_sch\_059 / FTE via EDFacts file specification FS059/DG644) is subtracted from the district's LEA-level teacher FTE count (ccd\_lea\_059 / FTE via FS059/DG528 using teacher-permitted values):

$$\\text{Traditional Teachers} \= \\text{FTE}\_{\\text{LEA Teachers}} \- \\sum \\text{FTE}\_{\\text{Charter School Teachers}}$$

### **Critical Limitation: Non-Teacher Staff**

While you can isolate classroom teachers, **it is impossible to isolate other instructional and support staff** (e.g., school psychologists, librarians, counselors, or instructional coordinators) for a dependent charter school using the CCD. The federal FS059 file specification only collects "Teachers (FTE)" (DG644) at the school level. All other non-teacher staff FTE categories are aggregated and reported exclusively at the LEA or State level. Therefore, any district-level equity metrics that rely on broader student-adult or support staff ratios cannot be separated by school sector.

## **Availability and Completeness of ccd\_sch\_059**

School-level staffing data (ccd\_sch\_059 / FTE) **does exist** in the CCD School Universe, but it is strictly limited to **FTE Classroom Teachers**. NCES defines a teacher at the school level as a professional staff member who instructs students and maintains daily attendance records.

These counts are complete enough to calculate a basic, nominal pupil-teacher ratio ($R\_{pt}$) for most brick-and-mortar schools across the country:

$$R\_{pt} \= \\frac{\\text{MEMBER}}{\\text{FTE}}$$  
Where $\\text{MEMBER}$ is the student enrollment count (ccd\_sch\_052) and $\\text{FTE}$ is the classroom teacher count (ccd\_sch\_059). However, relying on this ratio for rigorous equity or workload analysis carries severe caveats.

## **Key Coverage and Quality Caveats**

When utilizing ccd\_sch\_059 to construct school-level student-teacher ratios or to partition dependent charter staff, researchers face several well-documented anomalies:

### **1\. Vertical LEA-School Discrepancies (The "Roving" Teacher Problem)**

The sum of school-level teacher FTEs (ccd\_sch\_059) within a district rarely equals the reported district-level teacher FTE total (ccd\_lea\_059). Districts often centrally employ specialized teachers—such as art, music, or speech-language pathology specialists—who rotate across multiple physical campuses. Depending on how State Education Agencies (SEAs) report these teachers, they may either:

* Be omitted entirely from school-level files and reported only in the LEA directory, understating the actual teaching capacity at the school sites.

* Be fully reported at each individual campus they visit, leading to double-counting and an artificial inflation of teacher counts when aggregated.

### **2\. Complete State Reporting Omissions and Imputations**

The completeness of ccd\_sch\_059 is periodically compromised by state-level data submission failures. For example, in the 2014–15 and 2015–16 reporting cycles, Utah was unable to report staff data to EDFacts, forcing NCES to impute state-level staff metrics while school-level staff data remained missing. In the same cycles, Wyoming failed to report staff data at the LEA/school level entirely, resulting in all teacher values being set to \-1 (missing). More recently, states like Illinois have exhibited massive, unexplained shifts in staff FTE counts (FS059 / FS049) across cycles.

### **3\. Special Education Staffing Blind Spots**

School-level teacher FTE is reported as a single, generic category. It does not distinguish between general education teachers and special education teachers. Because dependent charters often enroll a different composition of students with disabilities and rely on the host district for self-contained special education staff, a nominal student-teacher ratio can be highly misleading.

State audits illustrate this volatility: when the Utah State Office of Education was audited, the omission of special education teachers from their initial pupil-teacher calculations distorted the statewide ratio by nearly 3 points, skewing it from 25.3 to 22.5 students per teacher.

### **4\. Administrative "Holder Records"**

According to the National Alliance for Public Charter Schools (NAPCS) "Modified Count System," charter networks and districts frequently use administrative placeholder files known as **Holder Records** to report data. These holder records are not physical schools, but they are used to aggregate enrollment and teacher metrics for multiple campuses. If a pipeline attempts to calculate school-level ratios without filtering out these records, it will generate highly distorted metrics: the administrative holder records will show artificially low student-teacher ratios (reflecting network-wide staff), while the actual physical campuses where instruction occurs may appear to have zero enrollment or zero teachers.

### **5\. Virtual and Online School Distortions**

If a dependent charter operates as a virtual or non-classroom-based program, its staffing structures are completely different from a traditional brick-and-mortar school. Virtual schools rely heavily on asynchronous learning and operate with much higher student-teacher ratios, averaging 24.4 students per teacher compared to the national physical average of 14.8.

If virtual charter staff are aggregated into the host geographic district's metrics, they distort the district-wide ratios, creating a false impression of local classroom crowding and teacher shortages. Analysts must filter out virtual schools (using the VIRTUAL flag) to maintain comparable staffing metrics.  
