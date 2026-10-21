/**
 * A snapshot of campaign FC-001 from the intelligence store, for the landing's
 * graph section to fall back on.
 *
 * The section loads the cluster live from `/api/intel/clusters/FC-001` and
 * uses this only when that request fails — the API is down, or it enforces
 * sign-in, which it does in production and an anonymous visitor to the
 * landing page does not have. It is the same data, not a stand-in: written
 * from that endpoint's own response on 2026-10-21, and the store that produced
 * it is deterministic.
 *
 * **The cases are synthetic.** `services/api/intel/repository.py` builds its
 * historical set with `seed_cases()`, which it describes as "deterministic,
 * clearly-synthetic". The section says so on screen, wherever this data is
 * shown, whether it came from here or from the API.
 */

import type { Cluster, GraphNode, RiskFactor } from "@/lib/api";

export const FC001_CAPTURED = "2026-10-21";

export const FC001_CLUSTER: Cluster = {
  "cluster_id": "FC-001",
  "size": 26,
  "primary_scam": "digital_arrest",
  "primary_scam_name": "Digital arrest / CBI impersonation",
  "shared_phones": [
    "7042118830",
    "8067459921",
    "9845012371",
    "9845012372"
  ],
  "shared_upi_ids": [
    "case.settle@okhdfcbank",
    "cbi.verify@okaxis",
    "refund.node@okicici"
  ],
  "shared_wallets": [],
  "states": [
    "Tamil Nadu",
    "Telangana",
    "Karnataka"
  ],
  "total_loss_inr": 59523500.0,
  "peak_threat": 96.2,
  "mean_threat": 89.3,
  "risk": "CRITICAL",
  "risk_score": 79.9,
  "case_ids": [
    "HFC-0001",
    "HFC-0002",
    "HFC-0003",
    "HFC-0004",
    "HFC-0005",
    "HFC-0006",
    "HFC-0007",
    "HFC-0008",
    "HFC-0009",
    "HFC-0010",
    "HFC-0011",
    "HFC-0012",
    "HFC-0013",
    "HFC-0014",
    "HFC-0015",
    "HFC-0016",
    "HFC-0017",
    "HFC-0018",
    "HFC-0019",
    "HFC-0020",
    "HFC-0021",
    "HFC-0022",
    "HFC-0023",
    "HFC-0024",
    "HFC-0025",
    "HFC-0026"
  ],
  "is_campaign": true
};

export const FC001_NODES: GraphNode[] = [
  {
    "id": "phone:9845012371",
    "kind": "phone",
    "label": "9845012371",
    "cases": 11,
    "threat": null
  },
  {
    "id": "case:HFC-0018",
    "kind": "case",
    "label": "HFC-0018",
    "cases": null,
    "threat": 82.6
  },
  {
    "id": "upi:cbi.verify@okaxis",
    "kind": "upi",
    "label": "cbi.verify@okaxis",
    "cases": 14,
    "threat": null
  },
  {
    "id": "case:HFC-0024",
    "kind": "case",
    "label": "HFC-0024",
    "cases": null,
    "threat": 87.9
  },
  {
    "id": "case:HFC-0020",
    "kind": "case",
    "label": "HFC-0020",
    "cases": null,
    "threat": 83.3
  },
  {
    "id": "case:HFC-0007",
    "kind": "case",
    "label": "HFC-0007",
    "cases": null,
    "threat": 96.2
  },
  {
    "id": "case:HFC-0014",
    "kind": "case",
    "label": "HFC-0014",
    "cases": null,
    "threat": 92.6
  },
  {
    "id": "phone:9845012372",
    "kind": "phone",
    "label": "9845012372",
    "cases": 13,
    "threat": null
  },
  {
    "id": "case:HFC-0009",
    "kind": "case",
    "label": "HFC-0009",
    "cases": null,
    "threat": 93.3
  },
  {
    "id": "case:HFC-0012",
    "kind": "case",
    "label": "HFC-0012",
    "cases": null,
    "threat": 80.4
  },
  {
    "id": "case:HFC-0010",
    "kind": "case",
    "label": "HFC-0010",
    "cases": null,
    "threat": 93.3
  },
  {
    "id": "case:HFC-0016",
    "kind": "case",
    "label": "HFC-0016",
    "cases": null,
    "threat": 87.8
  },
  {
    "id": "case:HFC-0026",
    "kind": "case",
    "label": "HFC-0026",
    "cases": null,
    "threat": 93.6
  },
  {
    "id": "case:HFC-0011",
    "kind": "case",
    "label": "HFC-0011",
    "cases": null,
    "threat": 88.8
  },
  {
    "id": "case:HFC-0022",
    "kind": "case",
    "label": "HFC-0022",
    "cases": null,
    "threat": 95.9
  },
  {
    "id": "case:HFC-0003",
    "kind": "case",
    "label": "HFC-0003",
    "cases": null,
    "threat": 87.3
  },
  {
    "id": "case:HFC-0015",
    "kind": "case",
    "label": "HFC-0015",
    "cases": null,
    "threat": 91.0
  },
  {
    "id": "case:HFC-0025",
    "kind": "case",
    "label": "HFC-0025",
    "cases": null,
    "threat": 80.5
  },
  {
    "id": "upi:refund.node@okicici",
    "kind": "upi",
    "label": "refund.node@okicici",
    "cases": 10,
    "threat": null
  },
  {
    "id": "case:HFC-0023",
    "kind": "case",
    "label": "HFC-0023",
    "cases": null,
    "threat": 96.1
  },
  {
    "id": "case:HFC-0021",
    "kind": "case",
    "label": "HFC-0021",
    "cases": null,
    "threat": 95.3
  },
  {
    "id": "case:HFC-0017",
    "kind": "case",
    "label": "HFC-0017",
    "cases": null,
    "threat": 87.6
  },
  {
    "id": "case:HFC-0005",
    "kind": "case",
    "label": "HFC-0005",
    "cases": null,
    "threat": 87.0
  },
  {
    "id": "case:HFC-0001",
    "kind": "case",
    "label": "HFC-0001",
    "cases": null,
    "threat": 81.5
  },
  {
    "id": "case:HFC-0002",
    "kind": "case",
    "label": "HFC-0002",
    "cases": null,
    "threat": 94.9
  },
  {
    "id": "case:HFC-0008",
    "kind": "case",
    "label": "HFC-0008",
    "cases": null,
    "threat": 89.7
  },
  {
    "id": "case:HFC-0006",
    "kind": "case",
    "label": "HFC-0006",
    "cases": null,
    "threat": 93.8
  },
  {
    "id": "upi:case.settle@okhdfcbank",
    "kind": "upi",
    "label": "case.settle@okhdfcbank",
    "cases": 14,
    "threat": null
  },
  {
    "id": "case:HFC-0019",
    "kind": "case",
    "label": "HFC-0019",
    "cases": null,
    "threat": 87.7
  },
  {
    "id": "phone:8067459921",
    "kind": "phone",
    "label": "8067459921",
    "cases": 4,
    "threat": null
  },
  {
    "id": "case:HFC-0013",
    "kind": "case",
    "label": "HFC-0013",
    "cases": null,
    "threat": 79.3
  },
  {
    "id": "case:HFC-0004",
    "kind": "case",
    "label": "HFC-0004",
    "cases": null,
    "threat": 95.5
  },
  {
    "id": "phone:7042118830",
    "kind": "phone",
    "label": "7042118830",
    "cases": 15,
    "threat": null
  }
];

/** Identifier → case, as the store reports them. */
export const FC001_EDGES: [string, string][] = [["phone:9845012371", "case:HFC-0004"], ["phone:9845012371", "case:HFC-0007"], ["phone:9845012371", "case:HFC-0008"], ["phone:9845012371", "case:HFC-0009"], ["phone:9845012371", "case:HFC-0010"], ["phone:9845012371", "case:HFC-0011"], ["phone:9845012371", "case:HFC-0013"], ["phone:9845012371", "case:HFC-0014"], ["phone:9845012371", "case:HFC-0016"], ["phone:9845012371", "case:HFC-0018"], ["phone:9845012371", "case:HFC-0026"], ["case:HFC-0018", "upi:case.settle@okhdfcbank"], ["upi:cbi.verify@okaxis", "case:HFC-0001"], ["upi:cbi.verify@okaxis", "case:HFC-0003"], ["upi:cbi.verify@okaxis", "case:HFC-0007"], ["upi:cbi.verify@okaxis", "case:HFC-0008"], ["upi:cbi.verify@okaxis", "case:HFC-0009"], ["upi:cbi.verify@okaxis", "case:HFC-0010"], ["upi:cbi.verify@okaxis", "case:HFC-0011"], ["upi:cbi.verify@okaxis", "case:HFC-0012"], ["upi:cbi.verify@okaxis", "case:HFC-0015"], ["upi:cbi.verify@okaxis", "case:HFC-0016"], ["upi:cbi.verify@okaxis", "case:HFC-0017"], ["upi:cbi.verify@okaxis", "case:HFC-0021"], ["upi:cbi.verify@okaxis", "case:HFC-0022"], ["upi:cbi.verify@okaxis", "case:HFC-0026"], ["case:HFC-0024", "phone:8067459921"], ["case:HFC-0024", "upi:refund.node@okicici"], ["case:HFC-0020", "phone:8067459921"], ["case:HFC-0020", "phone:9845012372"], ["case:HFC-0020", "upi:case.settle@okhdfcbank"], ["case:HFC-0020", "upi:refund.node@okicici"], ["case:HFC-0007", "upi:case.settle@okhdfcbank"], ["case:HFC-0014", "phone:9845012372"], ["case:HFC-0014", "upi:case.settle@okhdfcbank"], ["phone:9845012372", "case:HFC-0001"], ["phone:9845012372", "case:HFC-0002"], ["phone:9845012372", "case:HFC-0004"], ["phone:9845012372", "case:HFC-0005"], ["phone:9845012372", "case:HFC-0006"], ["phone:9845012372", "case:HFC-0008"], ["phone:9845012372", "case:HFC-0012"], ["phone:9845012372", "case:HFC-0016"], ["phone:9845012372", "case:HFC-0017"], ["phone:9845012372", "case:HFC-0023"], ["phone:9845012372", "case:HFC-0025"], ["case:HFC-0009", "upi:case.settle@okhdfcbank"], ["case:HFC-0012", "phone:7042118830"], ["case:HFC-0012", "upi:case.settle@okhdfcbank"], ["case:HFC-0016", "upi:case.settle@okhdfcbank"], ["case:HFC-0026", "phone:7042118830"], ["case:HFC-0026", "upi:case.settle@okhdfcbank"], ["case:HFC-0011", "phone:7042118830"], ["case:HFC-0022", "phone:7042118830"], ["case:HFC-0022", "upi:refund.node@okicici"], ["case:HFC-0003", "phone:8067459921"], ["case:HFC-0015", "phone:7042118830"], ["case:HFC-0015", "upi:refund.node@okicici"], ["case:HFC-0025", "upi:case.settle@okhdfcbank"], ["upi:refund.node@okicici", "case:HFC-0004"], ["upi:refund.node@okicici", "case:HFC-0005"], ["upi:refund.node@okicici", "case:HFC-0008"], ["upi:refund.node@okicici", "case:HFC-0013"], ["upi:refund.node@okicici", "case:HFC-0017"], ["upi:refund.node@okicici", "case:HFC-0023"], ["case:HFC-0023", "phone:7042118830"], ["case:HFC-0021", "phone:8067459921"], ["case:HFC-0001", "phone:7042118830"], ["case:HFC-0001", "upi:case.settle@okhdfcbank"], ["case:HFC-0002", "upi:case.settle@okhdfcbank"], ["case:HFC-0006", "upi:case.settle@okhdfcbank"], ["upi:case.settle@okhdfcbank", "case:HFC-0013"], ["upi:case.settle@okhdfcbank", "case:HFC-0019"], ["case:HFC-0019", "phone:7042118830"]];

export const FC001_FACTORS: RiskFactor[] = [
  {
    "factor": "Financial loss",
    "contribution": 0.232,
    "detail": "\u20b959,523,500 at risk"
  },
  {
    "factor": "Linked cases",
    "contribution": 0.168,
    "detail": "26 cases connected"
  },
  {
    "factor": "Reused infrastructure",
    "contribution": 0.127,
    "detail": "7 shared identifiers"
  },
  {
    "factor": "Module 1 peak threat",
    "contribution": 0.115,
    "detail": "peak 96/100"
  },
  {
    "factor": "Geographic spread",
    "contribution": 0.084,
    "detail": "3 states"
  },
  {
    "factor": "Network connectivity",
    "contribution": 0.071,
    "detail": "mean 89/100"
  }
];
