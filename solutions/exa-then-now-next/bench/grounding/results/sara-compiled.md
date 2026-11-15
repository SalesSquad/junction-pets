# SARA: compiled statute programs vs one question (2026-11-14)

272 assertions; Haiku marked 161 as handled by a program (no arithmetic). Programs see statute + assertion only. Balanced accuracy.

| verifier | all 272 (program, else one question) | handled only | unhandled only |
|---|---|---|---|
| jev: one question | 77 % | 83 % | 70 % |
| jev: compiled program | 79 % | 86 % | (one question) |
|  ↳ paired | program right & single wrong 17, reverse 12, exact McNemar p = 0.4583 | | |
| luna: one question | 65 % | 72 % | 56 % |
| luna: compiled program | 70 % | 81 % | (one question) |
|  ↳ paired | program right & single wrong 34, reverse 21, exact McNemar p = 0.1048 | | |

Formula errors: 0. Unhandled examples: "Section 2(a)(2)(B) applies to Bob in 2014."; "Under section 63(c)(3), Alice's additional standard deduction in 2017 is equal to $1200."; "Alice and her spouse have to pay $24543 in taxes for the year 2017 under section 1(a)(iii)."
