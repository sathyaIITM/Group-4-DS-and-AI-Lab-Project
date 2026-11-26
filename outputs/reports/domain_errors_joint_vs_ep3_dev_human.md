# Domain errors on dev_human: phase-2 joint Kev vs phase-1 ep3 and Jev

n = 198 (47 follow-up items, whose context already holds a result table). Raw argmax predictions; temperature scaling does not change the argmax. Selected phase-2 seed: joint_ep3_s1.

## ep3: 4 errors (accuracy 0.980); 1 on follow-up items

| id | label | predicted | max prob. (raw) | follow-up | message |
|---|---|---|---|---|---|
| dh-110 | other | unspecified | 0.92 | no | Can you help me fix a pandas merge error in my code? |
| dh-135 | labour | other | 1.00 | no | What other sources besides PLFS report joblessness? |
| dh-153 | multiple | health | 0.99 | yes | Which sources are these two numbers from? |
| dh-193 | multiple | labour | 0.76 | no | Did bad monsoons push up joblessness in Marathwada? use your data |

## joint_ep3_s0: 13 errors (accuracy 0.934); 6 on follow-up items; 10 that ep3 answers correctly

| id | label | predicted | max prob. (raw) | follow-up | message |
|---|---|---|---|---|---|
| dh-006 | prices_economy | other | 0.67 | yes | Turn this into a horizontal bar chart |
| dh-020 | multiple | prices_economy | 0.89 | no | Wheat MSP for 2022-23 and the CPI cereals index for March 2023, please |
| dh-042 | multiple | labour | 0.99 | yes | Overlay unemployment on this chart |
| dh-068 | other | health | 0.92 | no | Kya aapke paas literacy ka data hai? |
| dh-082 | prices_economy | other | 0.94 | yes | Make it a grouped bar chart by year |
| dh-117 | rainfall | agriculture | 0.96 | no | Total rainfall in Telangana for agricultural year 2014-15 |
| dh-123 | multiple | agriculture | 0.51 | no | Compare the wheat MSP with mandi wheat prices in 2020 |
| dh-135 | labour | other | 0.94 | no | What other sources besides PLFS report joblessness? |
| dh-141 | health | other | 0.71 | yes | Plot both side by side |
| dh-152 | prices_economy | other | 0.91 | yes | Chart it |
| dh-153 | multiple | health | 0.92 | yes | Which sources are these two numbers from? |
| dh-174 | unspecified | other | 0.73 | no | kitna tha 2021 mein? |
| dh-193 | multiple | labour | 0.99 | no | Did bad monsoons push up joblessness in Marathwada? use your data |

## joint_ep3_s1: 8 errors (accuracy 0.960); 5 on follow-up items; 4 that ep3 answers correctly

| id | label | predicted | max prob. (raw) | follow-up | message |
|---|---|---|---|---|---|
| dh-042 | multiple | labour | 1.00 | yes | Overlay unemployment on this chart |
| dh-100 | other | unspecified | 0.50 | yes | visualise the top 10 |
| dh-110 | other | unspecified | 1.00 | no | Can you help me fix a pandas merge error in my code? |
| dh-135 | labour | other | 0.98 | no | What other sources besides PLFS report joblessness? |
| dh-141 | health | other | 0.60 | yes | Plot both side by side |
| dh-153 | multiple | health | 0.97 | yes | Which sources are these two numbers from? |
| dh-188 | prices_economy | other | 0.95 | yes | Show the 2019-20 values as well |
| dh-193 | multiple | labour | 1.00 | no | Did bad monsoons push up joblessness in Marathwada? use your data |

## jev: 6 errors (accuracy 0.970); 3 on follow-up items; 5 that ep3 answers correctly

| id | label | predicted | max prob. (raw) | follow-up | message |
|---|---|---|---|---|---|
| dh-009 | health | other | 0.51 | yes | Add data labels |
| dh-042 | multiple | labour | 0.94 | yes | Overlay unemployment on this chart |
| dh-059 | rainfall | other | 0.44 | yes | bar chart banao |
| dh-065 | other | health | 0.55 | no | Road accident deaths in Tamil Nadu in 2022 |
| dh-123 | multiple | agriculture | 0.50 | no | Compare the wheat MSP with mandi wheat prices in 2020 |
| dh-193 | multiple | labour | 0.97 | no | Did bad monsoons push up joblessness in Marathwada? use your data |

