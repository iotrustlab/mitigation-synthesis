# Time extent of the water assurance claim

**UNSUPPORTED_BY_CURRENT_MODEL.** The nominal Remote and Hand programs establish water service at the assessment boundary. The three-scan model ends there.

| Property | Available evidence | Decision |
| --- | --- | --- |
| Reach the original 5 L/s threshold by request-relative tick three | The nominal complete programs reach 6.4 L/s and 49.2 psi at tick three. The box and executable witness check running, terminal flow, pressure, and time. | Established under the stated premises. |
| Preserve safety | The safety flag starts at the stopped state and checks flow, pressure, pH and protection at each of the three updates. | Established at the origin and three sample instants. |
| Remain above threshold after assessment | The plant has three ordered updates. Its clock, demand, flow and safety updates stop at the third one. Future motor power, drive demand, protection and path availability have no bound in the archive. | No trajectory or justified continuation for the requested dwell. |
| Renew observation | A single terminal meter stage samples flow and pressure, verifies freshness, and establishes correspondence. | One terminal reading is established. A fourth observation or subsequent freshness is unbound. |

The earlier assessments in the [service-region study](ATTLEBORO_SERVICE_REGION.md) each make one reading at the end of a different schedule. Combining endpoints from different programs cannot supply repeated readings along one run. H2's terminal sample at tick four follows a later start and misses the original deadline. The audit leaves the archived M0 and H0 theorems unchanged. [Plant and observer](../formal_model.py) · [M0 progress and evidence](../paper_v2/formal_evidence/proof_records/v2_M0) · [H0 progress and evidence](../paper_v2/formal_evidence/proof_records/v2_H0) · [Earlier duration audit](SUSTAINED_SERVICE_AUDIT.md)
