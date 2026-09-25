# Patient Fall Detection System — Project Brief
**Team:** Lazy Lobsters (Malaika Lusamaki, Edouard Cossin, Azhar Ahmed)
**Challenge Domain:** Healthcare Automation
**Event:** SU-CESI Hackathon
**Duration:** 1.5 Days

---

## 1. Project Overview

We are building a system that automatically detects when a hospital patient falls or collapses while unattended, and alerts the nearest available nurse with the room location and timestamp — without relying on a staff member being physically present at the moment it happens.

The core insight: nurses cannot watch every patient at every moment, so unwitnessed falls are currently found only when a nurse happens to pass by on the next round. Our system closes that gap using computer vision and pose estimation, while deliberately avoiding raw video capture to protect patient privacy.

---

## 2. The Problem

### 2.1 What Is Happening
Patients in hospital wards — particularly those at risk of falls, fainting, or sudden deterioration — fall while unassisted and unwitnessed, most often while trying to get up alone to reach the toilet. They are found only when a nurse next happens to pass by.

### 2.2 Who Is Affected
- **Fall-risk patients** who get up without help and cannot call out once they've fallen
- **Ward nurses** who cannot be at every bedside at once

### 2.3 Why It Matters
Roughly 1 in 3 inpatient falls causes injury. A fall that goes undiscovered for longer is more likely to escalate into a head injury, a fracture, a longer hospital stay, or ICU admission. The delay between the fall and its discovery — not just the fall itself — is what drives the worst outcomes.

### 2.4 What Happens If Nothing Changes
Patients will keep falling alone between rounds, and roughly a third of those falls will result in injury, with associated cost and clinical harm to the hospital and patient alike.

### 2.5 The Action Gap
There is currently no system that can detect an unassisted fall, confirm that it actually happened, and alert the nearest available nurse with the room number. These falls are still found only by chance.

---

## 3. Root Cause Analysis (Five Whys)

| Step | Why |
|---|---|
| 1 | The patient was not found quickly after their fall |
| 2 | No alert was triggered at the moment of the fall |
| 3 | No one was on-site to trigger the alert |
| 4 | There is no system in place to automatically detect falls |
| 5 | The facility does not have appropriate detection and alert technology |

**Root Cause:** Wards have no system that can notice an unassisted fall on its own, confirm it, and alert the right nurse — so a patient who goes down alone is found only on the next round, by which point the delay has increased both the clinical harm and the cost of the fall.

### Supporting Evidence
- Inpatient fall rates range from 1.7 to 25 falls per 1,000 patient days; roughly 1.9–3% of all hospitalizations involve a fall
- About 1 in 3 falls causes injury; under 1% are fatal — but this still amounts to around 11,000 hospital fall deaths a year in the US
- About 45% of inpatient falls are toileting-related, most commonly on the way from the bed or chair to the bathroom
- The greatest injury risk is the **unassisted fall**, where no one is present to break the descent

---

## 4. Final Problem Statement (IRCA Model)

> **Despite** the hospital's duty to keep fall-risk patients safe, and the cost it carries for every fall that occurs,
> **patients** who fall while alone and unable to call for help, and **the nurses** who cannot watch every bed at once,
> **experience** delayed discovery of the fall, because no one is present to see it and nothing privacy-safe is watching when staff are away.
> **This matters because** the longer a fallen patient lies undiscovered, the more likely the fall escalates into a serious injury — and one prevented escalation already outweighs the cost of the system.
> **However**, existing infrastructure cannot detect a fall, or decide who to alert.

---

## 5. Stakeholders

| Stakeholder | Type | Goals | Pain Points | Interest |
|---|---|---|---|---|
| Patient at Risk | Beneficiary | Receive rapid help when dizzy or collapsed | Unable to call for help when suddenly unwell or unconscious | 5/5 |
| Ward Nurses / Clinical Staff | User | Respond quickly to distress; monitor all patients | Cannot watch every patient at once; collapses between rounds go unnoticed | High |
| Hospital Management | Decision Maker | Improve patient safety outcomes; reduce liability | Limited staff per ward; pressure to prevent in-ward incidents | High |
| Healthcare Ministries / Regulators | Decision Maker | Improve safety standards; set deployment rules | No clear framework for autonomous AI monitoring; accountability gaps | Medium |
| Insurance Providers | Influencer | Reduce payouts via faster intervention | Unclear liability when AI triggers or fails to trigger an alert | Medium |
| AI / Computer Vision Team | Implementer | Build accurate, low-false-positive detection models | Detection ambiguity; occlusion; distinguishing collapse from normal rest | High |
| Hospital Rapid Response Team | Beneficiary | Reach deteriorating patients with advance warning | No early alert; arrive only after a collapse is manually reported | High |

---

## 6. Solution Concept (MVP Definition)

### 6.1 Who This Is For
Ward nurses and fall-risk inpatients, in the context of hospital wards where staff cannot maintain continuous one-to-one observation.

### 6.2 Problem It Solves
The delay between an unwitnessed fall and its discovery.

### 6.3 Core Function
A camera feed is processed in real time using a pose-estimation model. A rule engine analyzes the resulting skeleton data for fall-like motion (sudden drop in hip/shoulder height, horizontal body orientation, followed by stillness). When a fall is detected, an alert — including room ID and timestamp — is pushed to a nurse-facing dashboard.

### 6.4 Why Pose Data, Not Raw Video
Using skeleton/pose keypoints instead of raw video directly addresses the privacy concern embedded in our own problem statement ("nothing privacy-safe is watching when staff are away"). No identifiable footage is stored or transmitted — only joint coordinates and motion patterns.

### 6.5 Assumptions Being Tested
- A rule-based motion model (height drop + orientation + stillness) can distinguish a fall from normal activities like sitting, bending, or lying down with acceptable accuracy
- A single overhead/wall-mounted webcam angle is sufficient to capture the relevant motion
- Alert latency from fall to dashboard notification can be kept low enough to be clinically meaningful

### 6.6 Success Criteria
- Correctly flags simulated falls across multiple test scenarios
- Does not falsely flag sitting down, bending over, or lying down to rest
- Dashboard displays room ID, timestamp, and alert status within a few seconds of the event

### 6.7 In Scope (MVP)
- Single-camera pose detection
- Rule-based fall classifier
- Real-time dashboard (room ID, timestamp, alert status, skeleton snapshot)

### 6.8 Out of Scope (MVP)
- Dedicated hardware sensors (wearables, pressure mats)
- Mobile app for nurses
- Real SMS/push notification delivery to personal devices
- Multi-room/multi-camera deployment
- Persistent database storage (in-memory alert list is sufficient for a demo)

---

## 7. System Architecture

| Component | Description |
|---|---|
| **Users** | Ward nurses (recipients of alerts), hospital administrators (oversight) |
| **Inputs** | Live webcam video feed of a ward/room |
| **Processing** | Pose estimation model extracts skeleton keypoints → rule engine evaluates motion pattern → classifier flags fall vs. non-fall |
| **Outputs** | Alert containing room ID, timestamp, and skeleton snapshot, displayed on a dashboard |
| **Hardware** | Laptop with webcam (required); second laptop for separate dashboard display (optional) |
| **Software** | Python, OpenCV, MediaPipe (or TensorFlow.js/MoveNet for a browser-based version), lightweight web dashboard (HTML/JS or Flask) |
| **Data Flow** | Camera → frame capture → pose keypoint extraction → rule-based fall detection → alert generation → dashboard render |

### Architecture Diagram (textual)
```
[Webcam] → [Pose Estimation Model] → [Rule Engine: drop + orientation + stillness]
                                              ↓
                                     [Fall Detected? Y/N]
                                              ↓ (Y)
                              [Alert: Room ID + Timestamp + Snapshot]
                                              ↓
                                      [Nurse Dashboard]
```

---

## 8. Risk Register

| Risk | Probability | Impact | Mitigation |
|---|---|---|---|
| False positives (sitting/bending misclassified as falls) | Medium | Medium | Tune thresholds using varied test scenarios before demo |
| Occlusion or poor lighting affecting pose detection | Medium | Medium | Test camera placement and lighting conditions in advance |
| Network/local processing reliability | Low | Medium | Keep processing local rather than cloud-dependent for the demo |
| Privacy/consent concerns | Low | High | Use pose/skeleton data only, never raw video, as the core design choice |
| Time overrun on build | Medium | High | Freeze MVP scope early; cut stretch goals first if behind schedule |

---

## 9. What Is Needed

### 9.1 Hardware
- Laptop with a built-in or external webcam (required)
- A second laptop to display the dashboard separately from the detection feed (optional, improves demo clarity)

### 9.2 Software / Tools
- Python 3.x
- OpenCV (video capture and frame processing)
- MediaPipe or TensorFlow.js/MoveNet (pose estimation)
- Flask or plain HTML/JS (dashboard front end)
- Git repository for version control and collaboration

### 9.3 Test Data
- Team members physically simulating falls, sitting, bending, and lying down
- Backup: publicly available clips from the UR Fall Detection Dataset, in case live simulation isn't sufficient for the demo

### 9.4 Team Roles
| Member | Strengths | Responsibility |
|---|---|---|
| Malaika | AI/ML, Web Dev, UI/UX, Data Analysis | Detection model + dashboard build |
| Azhar | AI/ML, Web Dev, Programming, Mobile/Cloud | Detection model + dashboard build |
| Edouard | Communication, Business Analysis, Process Improvement | System framing, business case, structured testing |
| All | — | Testing rotation, pitch rehearsal, daily reflection |

---

## 10. Testing Plan

| Test Scenario | Objective |
|---|---|
| Fall from standing | Confirm detection of the primary target event |
| Fall near bed edge | Confirm detection in a realistic ward layout |
| Sitting down quickly | Confirm this is NOT flagged as a fall |
| Bending to pick something up | Confirm this is NOT flagged as a fall |
| Lying down to rest | Confirm this is NOT flagged as a fall |

Results should be logged with: date, observations, pass/partial/fail status, evidence collected (screenshots/clips), and any required improvements.

---

## 11. Timeline

### Day 1 (9:00–22:00) — Build
- **Morning:** Finalize Challenge Pitch, User Journey, Evidence Review, Assumption Validation, Architecture sketch, Risk Register
- **Midday–Afternoon:** Build pose detection, fall classifier, dashboard; run first integration test
- **Evening:** Stretch goals if ahead of schedule, otherwise bug fixing and stabilization; Daily Reflection

### Day 2 (9:00–14:30) — Test, Package, Pitch
- **Morning:** Run formal Testing Plan across all scenarios; freeze feature set
- **Midday:** Build final presentation deck, split by team strength
- **Afternoon:** Full timed dry run with live demo, record backup video, final polish, submit

---

## 12. Fallback Plan (If Behind Schedule)

Cut features in this order, stopping as soon as the timeline recovers:
1. Cloud/mobile notifications
2. Nurse "acknowledge" button/flow
3. Multi-room simulation (one room is sufficient for the demo)
4. Persistent database storage (in-memory alert list is acceptable)

---

## 13. Final Presentation Structure

| Slide | Content |
|---|---|
| 1 | Team Introduction |
| 2 | Problem Statement (IRCA model) |
| 3 | Stakeholders |
| 4 | Evidence & Insights — "We observed that... This suggests that... Because... Therefore..." |
| 5 | Root Causes |
| 6 | Solution Concept |
| 7 | System Architecture |
| 8 | Prototype Demonstration |
| 9 | Validation & Testing Results |
| 10 | Impact & Future Development |