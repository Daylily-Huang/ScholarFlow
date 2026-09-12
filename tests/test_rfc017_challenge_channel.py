# -*- coding: utf-8 -*-
"""RFC-017 反证（CHALLENGE）通道的自动回归。

四项用户裁定全部落成断言：

1. 反证**必须有人工复核**（缺复核 → `PENDING_HUMAN_CONFIRMATION`）；
2. 反证**参与综合加权**，但封顶且不得构成"反证多数决"；
3. 反证有**强度分级**（`WEAKENS` / `REFUTES`，后者须给 `refutation_basis`）；
4. 跨语言/绑定门槛与 SUPPORT **同级**（同样要求溯源、定位、范围与命题指纹绑定）。

不变量：`alignment` 对非 SUPPORT 关系**永远不是 VERIFIED**。
"""

import json
import os
import sys
import tempfile
import unittest

import helpers  # noqa: F401

from shared.execution import SessionStore, to_evidence_link  # noqa: E402

REPO_ROOT = helpers.REPO_ROOT
sys.path.insert(0, os.path.join(REPO_ROOT, "skills", "literature-synthesis", "scripts"))

from controversy_analyzer import (  # noqa: E402
    apply_verified_challenges,
    challenge_penalty,
    compute_topic_consensus,
)

PROP = "黑麂与小麂的共存主轴是空间与时间生态位分化。"
CHALLENGE_QUOTE = ("冬季由于可利用的资源减少，竞争加剧，二者通过调整日活动节律，"
                   "增加时间生态位分化程度，从而实现同域共存。")
SUPPORTING_QUOTE = PROP
IRRELEVANT_QUOTE = "本研究采用双因素方差分析比较三种配置的土壤理化性质。"


def _store(folder, event_id="EV-CH-1", actor="user", execution_kind="USER",
           event_type="EVIDENCE_IMPORTED", applied=True):
    store = SessionStore(folder)
    store.append_event({"schema_version": "0.1", "event_id": event_id, "session_id": "S1",
                        "seq": 1, "type": event_type, "actor": actor,
                        "execution_kind": execution_kind, "payload": {},
                        "created_at": None, "applied": applied})
    return store


def _credential(event_id="EV-CH-1", strength="WEAKENS", scope="MECHANISM", **over):
    cred = {"status": "VERIFIED", "challenge_scope": scope, "challenge_strength": strength,
            "verifier": "host-agent", "verification_ref": "audit/report_challenge.json",
            "human_confirmation": {"confirmed_by": "user", "confirmed_event_id": event_id}}
    cred.update(over)
    return cred


def _record(quote=CHALLENGE_QUOTE, credential=None, **over):
    rec = {"evidence_id": "EV-CH", "artifact_ref": "hu_temporal_spatial.pdf",
           "verbatim_quote": quote, "location": {"page": 9, "section": "讨论"},
           "checked_scope": "全文 11 页", "claim_status": "supported", "idea_version": 2}
    if credential is not None:
        rec["challenge_verification"] = credential
    rec.update(over)
    return rec


class TestChallengeStateMachine(unittest.TestCase):

    def test_missing_credential_is_unresolved(self):
        link = to_evidence_link(_record(), PROP, "CHALLENGE")
        self.assertEqual(link["challenge_status"], "UNRESOLVED")
        self.assertEqual(link["alignment"], "UNRESOLVED")

    def test_missing_human_confirmation_is_pending(self):
        """裁定 1：反证必须人工复核，缺复核只能停在待确认，不得算已核验。"""
        cred = _credential()
        cred.pop("human_confirmation")
        link = to_evidence_link(_record(credential=cred), PROP, "CHALLENGE")
        self.assertEqual(link["challenge_status"], "PENDING_HUMAN_CONFIRMATION")

    def test_confirmation_without_trusted_store_is_pending(self):
        link = to_evidence_link(_record(credential=_credential()), PROP, "CHALLENGE")
        self.assertEqual(link["challenge_status"], "PENDING_HUMAN_CONFIRMATION")

    def test_confirmation_event_must_exist_in_trusted_log(self):
        with tempfile.TemporaryDirectory(prefix="sf-rfc017-") as folder:
            store = _store(folder, event_id="EV-OTHER")
            link = to_evidence_link(_record(credential=_credential()), PROP, "CHALLENGE",
                                    session_store=store)
            self.assertEqual(link["challenge_status"], "PENDING_HUMAN_CONFIRMATION")
            self.assertIn("not found", link["challenge_reason"])

    def test_non_user_event_cannot_confirm(self):
        with tempfile.TemporaryDirectory(prefix="sf-rfc017-") as folder:
            store = _store(folder, actor="moderator", execution_kind="ROLE_SWITCH")
            link = to_evidence_link(_record(credential=_credential()), PROP, "CHALLENGE",
                                    session_store=store)
            self.assertEqual(link["challenge_status"], "REJECTED")

    def test_unapplied_event_cannot_confirm(self):
        with tempfile.TemporaryDirectory(prefix="sf-rfc017-") as folder:
            store = _store(folder, applied=False)
            link = to_evidence_link(_record(credential=_credential()), PROP, "CHALLENGE",
                                    session_store=store)
            self.assertEqual(link["challenge_status"], "PENDING_HUMAN_CONFIRMATION")

    def test_verified_challenge_upgrades_without_touching_alignment(self):
        with tempfile.TemporaryDirectory(prefix="sf-rfc017-") as folder:
            store = _store(folder)
            link = to_evidence_link(_record(credential=_credential()), PROP, "CHALLENGE",
                                    session_store=store)
            self.assertEqual(link["challenge_status"], "VERIFIED_CHALLENGE")
            self.assertEqual(link["challenge_scope"], "MECHANISM")
            self.assertEqual(link["challenge_strength"], "WEAKENS")
            # 不变量：非 SUPPORT 关系永远不是 VERIFIED
            self.assertEqual(link["alignment"], "UNRESOLVED")
            self.assertEqual(link["challenge_basis"]["confirmed_event_id"], "EV-CH-1")

    def test_supporting_quote_cannot_be_registered_as_challenge(self):
        with tempfile.TemporaryDirectory(prefix="sf-rfc017-") as folder:
            store = _store(folder)
            link = to_evidence_link(_record(quote=SUPPORTING_QUOTE, credential=_credential()),
                                    PROP, "CHALLENGE", session_store=store)
            self.assertEqual(link["challenge_status"], "REJECTED")

    def test_irrelevant_quote_cannot_be_registered_as_challenge(self):
        with tempfile.TemporaryDirectory(prefix="sf-rfc017-") as folder:
            store = _store(folder)
            link = to_evidence_link(_record(quote=IRRELEVANT_QUOTE, credential=_credential()),
                                    PROP, "CHALLENGE", session_store=store)
            self.assertEqual(link["challenge_status"], "REJECTED")

    def test_refutes_requires_refutation_basis(self):
        """裁定 3：强度分级；REFUTES 必须给出凭什么说推翻。"""
        with tempfile.TemporaryDirectory(prefix="sf-rfc017-") as folder:
            store = _store(folder)
            cred = _credential(strength="REFUTES")
            link = to_evidence_link(_record(credential=cred), PROP, "CHALLENGE",
                                    session_store=store)
            self.assertEqual(link["challenge_status"], "UNRESOLVED")
            cred["refutation_basis"] = "同地点同方法实测重叠 0.86，与原命题预测相反"
            link = to_evidence_link(_record(credential=cred), PROP, "CHALLENGE",
                                    session_store=store)
            self.assertEqual(link["challenge_status"], "VERIFIED_CHALLENGE")
            self.assertEqual(link["challenge_strength"], "REFUTES")

    def test_illegal_scope_or_strength_is_refused(self):
        with tempfile.TemporaryDirectory(prefix="sf-rfc017-") as folder:
            store = _store(folder)
            for bad in ({"challenge_scope": "VIBES"}, {"challenge_strength": "DESTROYS"}):
                cred = _credential(**bad)
                link = to_evidence_link(_record(credential=cred), PROP, "CHALLENGE",
                                        session_store=store)
                self.assertEqual(link["challenge_status"], "UNRESOLVED", bad)

    def test_missing_binding_is_unresolved(self):
        """裁定 4：绑定门槛与 SUPPORT 同级。"""
        with tempfile.TemporaryDirectory(prefix="sf-rfc017-") as folder:
            store = _store(folder)
            for over in ({"artifact_ref": ""}, {"location": {"page": None}},
                         {"checked_scope": ""}):
                rec = _record(credential=_credential(), **over)
                link = to_evidence_link(rec, PROP, "CHALLENGE", session_store=store)
                self.assertEqual(link["challenge_status"], "UNRESOLVED", over)

    def test_support_relation_has_no_challenge_status(self):
        link = to_evidence_link(_record(quote=SUPPORTING_QUOTE, artifact_ref="p.pdf"),
                                PROP, "SUPPORT")
        self.assertEqual(link["challenge_status"], "UNRESOLVED")


class TestChallengeWeighting(unittest.TestCase):

    def test_penalty_scales_with_strength(self):
        weak = [{"challenge_status": "VERIFIED_CHALLENGE", "challenge_strength": "WEAKENS",
                 "independence_group_id": "G1"}]
        strong = [{"challenge_status": "VERIFIED_CHALLENGE", "challenge_strength": "REFUTES",
                   "independence_group_id": "G1"}]
        self.assertEqual(apply_verified_challenges(1.0, weak)[0], 0.75)
        self.assertEqual(apply_verified_challenges(1.0, strong)[0], 0.5)

    def test_same_group_penalty_is_capped(self):
        many = [{"challenge_status": "VERIFIED_CHALLENGE", "challenge_strength": "WEAKENS",
                 "independence_group_id": "G1"} for _ in range(4)]
        adjusted, factors = apply_verified_challenges(1.0, many)
        self.assertEqual(adjusted, 0.5)
        self.assertTrue(any("capped" in f for f in factors))

    def test_unverified_challenges_have_zero_effect(self):
        pends = [{"challenge_status": "PENDING_HUMAN_CONFIRMATION",
                  "challenge_strength": "REFUTES", "independence_group_id": "G1"}]
        self.assertEqual(apply_verified_challenges(1.0, pends), (1.0, []))

    def test_weight_never_goes_negative(self):
        heavy = [{"challenge_status": "VERIFIED_CHALLENGE", "challenge_strength": "REFUTES",
                  "independence_group_id": "G%d" % i} for i in range(6)]
        self.assertEqual(apply_verified_challenges(0.4, heavy)[0], 0.0)

    def _claims(self):
        return [
            {"claim_id": "C1", "paper_id": "P1", "independence_group_id": "G1",
             "stance": "SUPPORT", "evidence_strength": "DIRECT_EMPIRICAL",
             "support_type": "EXPLICIT", "extracted_value": "55.4%"},
            {"claim_id": "C2", "paper_id": "P2", "independence_group_id": "G2",
             "stance": "SUPPORT", "evidence_strength": "DIRECT_EMPIRICAL",
             "support_type": "EXPLICIT", "extracted_value": "0.86"},
        ]

    def _challenge(self, cid, target, strength="REFUTES"):
        return {"claim_id": cid, "paper_id": "PC-" + cid, "independence_group_id": "GC-" + cid,
                "relation": "CHALLENGE", "challenge_status": "VERIFIED_CHALLENGE",
                "challenge_strength": strength, "target_claim_id": target}

    def test_challenge_reduces_weight_of_target_claim(self):
        base = compute_topic_consensus(self._claims())
        adjusted = compute_topic_consensus(self._claims() + [self._challenge("CH1", "C2", "WEAKENS")])
        self.assertEqual(base["stance_weights"]["SUPPORT"], 2.0)
        self.assertEqual(adjusted["stance_weights"]["SUPPORT"], 1.75)
        self.assertEqual(adjusted["challenge_adjustment"]["targets"], ["C2"])

    def test_challenge_records_are_not_counted_as_stance_evidence(self):
        """反证记录不得同时充当 REFUTE 立场证据（否则就是多数决）。"""
        result = compute_topic_consensus(self._claims() + [self._challenge("CH1", "C2")])
        self.assertEqual(result["stance_weights"]["REFUTE"], 0.0)
        self.assertEqual(result["excluded_from_consensus"]["CHALLENGE_EVIDENCE"], 1)

    def test_many_challenges_never_flip_to_refute_majority(self):
        """5 条已核验反证只能把支持压到证据不足，绝不产生 REFUTE 多数。"""
        many = self._claims() + [self._challenge("CH%d" % i, "C1") for i in range(5)]
        result = compute_topic_consensus(many)
        self.assertEqual(result["stance_weights"]["REFUTE"], 0.0)
        self.assertEqual(result["consensus_classification"], "INSUFFICIENT_EVIDENCE")

    def test_pending_challenge_changes_nothing(self):
        pending = dict(self._challenge("CH1", "C2"),
                       challenge_status="PENDING_HUMAN_CONFIRMATION")
        result = compute_topic_consensus(self._claims() + [pending])
        self.assertEqual(result["stance_weights"]["SUPPORT"], 2.0)

    def test_penalty_helper_reports_factors(self):
        penalty, factors = challenge_penalty([self._challenge("CH1", "C1", "WEAKENS")])
        self.assertEqual(penalty, 0.25)
        self.assertTrue(any("challenge(" in f for f in factors))


if __name__ == "__main__":
    unittest.main()
