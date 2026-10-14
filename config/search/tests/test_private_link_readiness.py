"""Offline tests using synthetic values in publicly documented wire shapes.

Evidence:
https://learn.microsoft.com/en-us/azure/search/search-indexer-howto-access-private
Sections 2/3 document Microsoft-managed endpoint ownership and source GET
approval/readiness (the example omits id). Storage PECs contain Network PE IDs:
https://learn.microsoft.com/en-us/rest/api/storagerp/private-endpoint-connections/list?view=rest-storagerp-2023-05-01
Neither establishes a target-to-Search/link identity binding for auto-approval.
"""

from copy import deepcopy
import json
from pathlib import Path
import unittest
from unittest.mock import Mock, patch
from urllib.parse import urlsplit

from azure.core.exceptions import AzureError, ClientAuthenticationError
from azure.identity import CredentialUnavailableError
import requests

from config.search import private_link_readiness as readiness
from config.search import setup


PREFIX = "/subscriptions/11111111-1111-1111-1111-111111111111/resourceGroups/test/providers/"
SEARCH = PREFIX + "Microsoft.Search/searchServices/application-search"
STORAGE = PREFIX + "Microsoft.Storage/storageAccounts/documents"
FOUNDRY = PREFIX + "Microsoft.CognitiveServices/accounts/models"
DEFINITIONS = {"knowledgeSources": [{
    "name": "documents-native", "kind": "azureBlob",
    "azureBlobParameters": {"connectionString": f"ResourceId={STORAGE}"},
}]}
CONTEXT = {
    "NETWORK_ISOLATION": "true", "RETRIEVAL_BACKEND": "foundry_iq",
    "FOUNDRY_IQ_PATTERN": "azureBlob",
    "SEARCH_SERVICE_RESOURCE_ID": SEARCH, "STORAGE_ACCOUNT_RESOURCE_ID": STORAGE,
    "AI_FOUNDRY_ACCOUNT_RESOURCE_ID": FOUNDRY,
    "SEARCH_SERVICE_QUERY_ENDPOINT": "https://application-search.search.windows.net",
    "SEARCH_API_VERSION": "2025-05-01",
}


def response(body=None, status=200):
    result = Mock(status_code=status)
    result.json.return_value = body
    return result


class MockArm:
    """Learn section 3 source GET shape; no invented positive target bindings."""

    def __init__(self, context=None, *, approved=True, include_id=True):
        self.search, links = readiness._expected_links(context or CONTEXT)
        self.sources = {}
        for link in links:
            resource = {
                "name": link.name,
                "properties": {
                    "privateLinkResourceId": link.target, "groupId": link.group,
                    "status": "Approved" if approved else "Pending",
                    "provisioningState": "Succeeded",
                    "requestMessage": "Message text is not identity evidence.",
                    "resourceRegion": None,
                },
            }
            if include_id:
                resource["id"] = link.resource_id(self.search)
            self.sources[link.resource_id(self.search)] = resource
        self.force_status = None

    def request(self, method, url, *, headers, timeout, allow_redirects):
        assert method == "GET", "No approval writes are authorized by this guarded implementation."
        assert headers["Authorization"] == "Bearer offline-token"
        assert 0 < timeout <= 30
        assert allow_redirects is False
        parsed = urlsplit(url)
        assert parsed.netloc == "management.azure.com"
        assert parsed.query == f"api-version={readiness.SEARCH_API_VERSION}"
        assert parsed.path in self.sources, "No target PEC or unrelated Search reads."
        if self.force_status:
            return response(status=self.force_status)
        return response(deepcopy(self.sources[parsed.path]))


class PrivateLinkReadinessTests(unittest.TestCase):
    def setUp(self):
        self.credential = Mock()
        self.credential.get_token.return_value.token = "offline-token"
        self.clock = 0
        self.network = patch.object(readiness.requests, "request").start()
        self.addCleanup(patch.stopall)
        patch.object(readiness.time, "monotonic", side_effect=lambda: self.clock).start()
        patch.object(readiness.time, "sleep", side_effect=self.sleep).start()

    def sleep(self, duration):
        self.clock += duration

    def run_gate(self, arm, context=None, definitions=None):
        self.network.side_effect = arm.request
        readiness.ensure_native_blob_private_links(
            definitions or DEFINITIONS, context or CONTEXT, self.credential,
            timeout_seconds=3, poll_seconds=1,
        )

    def test_documented_source_shape_with_or_without_id_is_authoritative_and_idempotent(self):
        for include_id in (False, True):
            with self.subTest(include_id=include_id):
                self.network.reset_mock()
                arm = MockArm(include_id=include_id)
                self.run_gate(arm)
                self.assertEqual(self.network.call_count, 4)
                self.assertEqual(self.clock, 0)
        self.credential.get_token.assert_called_with("https://management.azure.com/.default")

    def test_pending_is_immediate_actionable_admin_gate_without_target_reads_or_writes(self):
        arm = MockArm(approved=False)
        with self.assertRaisesRegex(readiness.PrivateLinkReadinessError, "Administrator approval required") as caught:
            self.run_gate(arm)
        for identity in (SEARCH, STORAGE, "blob", "spl-application-search-blob-0"):
            self.assertIn(identity, str(caught.exception))
        self.assertIn("Microsoft-managed", str(caught.exception))
        self.assertIn("No target requests are automatically approved", str(caught.exception))
        self.assertEqual(self.clock, 0)
        self.assertEqual(self.network.call_count, 1)

    def test_admin_approved_source_never_enumerates_opaque_or_paginated_target_pecs(self):
        # These target responses must never be requested, even when they contain
        # multiple pages, duplicate matches or malicious nextLink destinations.
        opaque_endpoint = PREFIX.replace("11111111", "22222222") + "Microsoft.Network/privateEndpoints/opaque"
        target_pec = {"name": "opaque", "properties": {
            "privateEndpoint": {"id": opaque_endpoint},
            "privateLinkServiceConnectionState": {"status": "Approved"},
        }}
        for next_link in (
            "https://untrusted.example/steal-token",
            f"{readiness.ARM_ENDPOINT}{STORAGE}/privateEndpointConnections?api-version=2023-05-01&$skiptoken=two",
            f"{readiness.ARM_ENDPOINT}{FOUNDRY}/privateEndpointConnections?api-version=wrong",
        ):
            with self.subTest(next_link=next_link):
                self.network.reset_mock()
                arm = MockArm()
                def provider(method, url, **kwargs):
                    if "/privateEndpointConnections" in url:
                        return response({"value": [target_pec, target_pec], "nextLink": next_link})
                    return arm.request(method, url, **kwargs)
                self.network.side_effect = provider
                readiness.ensure_native_blob_private_links(DEFINITIONS, CONTEXT, self.credential)
                self.assertEqual(self.network.call_count, 4)
                self.assertTrue(all("/privateEndpointConnections" not in call.args[1] for call in self.network.call_args_list))

    def test_source_request_message_and_next_link_never_authorize_approval_or_navigation(self):
        arm = MockArm(approved=False)
        source = next(iter(arm.sources.values()))
        source["nextLink"] = "https://untrusted.example"
        source["properties"]["requestMessage"] = f"Approve {SEARCH}, blob, deployment-owned"
        with self.assertRaisesRegex(readiness.PrivateLinkReadinessError, "Administrator approval"):
            self.run_gate(arm)
        self.assertEqual(self.network.call_count, 1)

    def test_approved_but_not_succeeded_waits_for_propagation_without_writes(self):
        arm = MockArm()
        source = next(iter(arm.sources.values()))
        source["properties"]["provisioningState"] = "Updating"
        def propagate(duration):
            self.sleep(duration)
            source["properties"]["provisioningState"] = "Succeeded"
        readiness.time.sleep.side_effect = propagate
        self.run_gate(arm)
        self.assertEqual(self.clock, 1)
        self.assertEqual(self.network.call_count, 5)

    def test_approved_but_unsucceeded_is_bounded(self):
        arm = MockArm()
        for source in arm.sources.values():
            source["properties"]["provisioningState"] = "Updating"
        with self.assertRaisesRegex(readiness.PrivateLinkReadinessError, "Timed out"):
            self.run_gate(arm)
        self.assertEqual(self.clock, 3)

    def test_wrong_source_identity_target_group_or_name_fails_closed(self):
        for field, wrong in (
            ("id", SEARCH + "/sharedPrivateLinkResources/other"),
            ("name", "other"), ("privateLinkResourceId", FOUNDRY), ("groupId", "file"),
        ):
            with self.subTest(field=field):
                arm = MockArm()
                source = next(iter(arm.sources.values()))
                (source if field in {"id", "name"} else source["properties"])[field] = wrong
                with self.assertRaisesRegex(readiness.PrivateLinkReadinessError, "identity mismatch"):
                    self.run_gate(arm)
                self.assertEqual(self.clock, 0)

    def test_denied_source_read_requires_search_permission_and_is_not_swallowed(self):
        for status in (401, 403):
            with self.subTest(status=status):
                arm = MockArm()
                arm.force_status = status
                with self.assertRaisesRegex(readiness.PrivateLinkReadinessError, "sharedPrivateLinkResources/read"):
                    self.run_gate(arm)
                self.assertEqual(self.clock, 0)

    def test_rejection_disconnection_and_failed_states_not_overridden(self):
        for field, state in (
            ("status", "Rejected"), ("status", "Disconnected"),
            ("provisioningState", "Failed"), ("provisioningState", "Canceled"),
        ):
            with self.subTest(field=field, state=state):
                arm = MockArm()
                next(iter(arm.sources.values()))["properties"][field] = state
                with self.assertRaisesRegex(readiness.PrivateLinkReadinessError, "administrator"):
                    self.run_gate(arm)
                self.assertEqual(self.clock, 0)

    def test_missing_source_and_transient_provider_errors_are_bounded(self):
        for status in (404, 429, 503):
            with self.subTest(status=status):
                self.clock = 0
                arm = MockArm()
                arm.force_status = status
                with self.assertRaisesRegex(readiness.PrivateLinkReadinessError, "Timed out"):
                    self.run_gate(arm)
                self.assertEqual(self.clock, 3)

    def test_narrow_transport_and_azure_auth_errors_are_sanitized(self):
        for boundary, error in (
            (self.network, requests.Timeout("secret")),
            (self.network, requests.ConnectionError("secret")),
            (self.credential.get_token, AzureError("secret")),
            (self.credential.get_token, ClientAuthenticationError("secret")),
            (self.credential.get_token, CredentialUnavailableError("secret")),
        ):
            with self.subTest(error=type(error).__name__):
                self.credential.get_token.side_effect = None
                self.network.side_effect = None
                boundary.side_effect = error
                with self.assertRaisesRegex(readiness.PrivateLinkReadinessError, "connectivity") as caught:
                    readiness.ensure_native_blob_private_links(DEFINITIONS, CONTEXT, self.credential)
                self.assertNotIn("secret", str(caught.exception))
        self.network.side_effect = None
        self.credential.get_token.side_effect = ClientAuthenticationError("secret-token")
        with self.assertRaises(readiness.PrivateLinkReadinessError) as caught:
            readiness.ensure_native_blob_private_links(DEFINITIONS, CONTEXT, self.credential)
        self.assertNotIn("secret-token", str(caught.exception))

    def test_unexpected_programming_errors_are_not_caught_as_azure_failures(self):
        for boundary in (self.network, self.credential.get_token):
            with self.subTest(boundary=boundary):
                self.network.side_effect = None
                self.credential.get_token.side_effect = None
                boundary.side_effect = TypeError("programming defect")
                with self.assertRaisesRegex(TypeError, "programming defect"):
                    readiness.ensure_native_blob_private_links(DEFINITIONS, CONTEXT, self.credential)

    def test_invalid_response_and_missing_readiness_fields_fail_closed(self):
        for body in ([], {}, {"name": "spl-application-search-blob-0", "properties": {}}):
            self.network.side_effect = None
            self.network.return_value = response(body)
            with self.assertRaises(readiness.PrivateLinkReadinessError):
                readiness.ensure_native_blob_private_links(DEFINITIONS, CONTEXT, self.credential)
        for field in ("status", "provisioningState"):
            arm = MockArm()
            del next(iter(arm.sources.values()))["properties"][field]
            with self.assertRaisesRegex(readiness.PrivateLinkReadinessError, "Missing status"):
                self.run_gate(arm)
        self.network.side_effect = None
        self.network.return_value = response()
        self.network.return_value.json.side_effect = ValueError("invalid-json-secret")
        with self.assertRaisesRegex(readiness.PrivateLinkReadinessError, "Invalid JSON"):
            readiness.ensure_native_blob_private_links(DEFINITIONS, CONTEXT, self.credential)

    def test_unknown_or_non_string_status_does_not_leak_provider_content(self):
        for status in ("secret-provider-details", ["secret-provider-details"], None):
            with self.subTest(status=status):
                arm = MockArm()
                next(iter(arm.sources.values()))["properties"]["status"] = status
                with self.assertRaises(readiness.PrivateLinkReadinessError) as caught:
                    self.run_gate(arm)
                self.assertNotIn("secret-provider-details", str(caught.exception))
                self.assertEqual(self.clock, 0)

    def test_gate_scope_excludes_non_native_non_isolated_and_search_index(self):
        for context, definitions in (
            ({**CONTEXT, "NETWORK_ISOLATION": "false"}, DEFINITIONS),
            ({**CONTEXT, "RETRIEVAL_BACKEND": "classic"}, DEFINITIONS),
            ({**CONTEXT, "FOUNDRY_IQ_PATTERN": "searchIndex"}, DEFINITIONS),
            (CONTEXT, {"knowledgeSources": [{"name": "index", "kind": "searchIndex"}]}),
            (CONTEXT, {"knowledgeSources": [{"name": "other", "kind": "mcpServer"}]}),
            (CONTEXT, {"knowledgeSources": []}),
        ):
            readiness.ensure_native_blob_private_links(definitions, context, self.credential)
        self.network.assert_not_called()
        self.credential.get_token.assert_not_called()

    def test_invalid_manifest_resource_ids_and_source_targets_fail_before_arm(self):
        _, links = readiness._expected_links(CONTEXT)
        manifest = [{"name": link.name, "groupId": link.group, "privateLinkResourceId": link.target} for link in links]
        for context in (
            {**CONTEXT, "SEARCH_SERVICE_RESOURCE_ID": SEARCH + "?redirect=bad"},
            {**CONTEXT, "SEARCH_SHARED_PRIVATE_LINKS": "not-json"},
            {**CONTEXT, "SEARCH_SHARED_PRIVATE_LINKS": []},
            {**CONTEXT, "SEARCH_SHARED_PRIVATE_LINKS": [*manifest[:-1], manifest[0]]},
            {**CONTEXT, "SEARCH_SHARED_PRIVATE_LINKS": [{**manifest[0], "name": ".."}, *manifest[1:]]},
            {**CONTEXT, "SEARCH_SHARED_PRIVATE_LINKS": [{**manifest[0], "groupId": []}, *manifest[1:]]},
            {**CONTEXT, "SEARCH_SHARED_PRIVATE_LINKS": [{**manifest[0], "privateLinkResourceId": FOUNDRY}, *manifest[1:]]},
        ):
            with self.assertRaises(readiness.PrivateLinkReadinessError):
                readiness.ensure_native_blob_private_links(DEFINITIONS, context, self.credential)
        wrong_source = deepcopy(DEFINITIONS)
        wrong_source["knowledgeSources"][0]["azureBlobParameters"]["connectionString"] = f"ResourceId={FOUNDRY}"
        with self.assertRaises(readiness.PrivateLinkReadinessError):
            readiness.ensure_native_blob_private_links(wrong_source, CONTEXT, self.credential)
        self.network.assert_not_called()

    def test_exact_bounded_names_adopted_from_template_manifest(self):
        context = {**CONTEXT, "SEARCH_SERVICE_RESOURCE_ID": SEARCH + "-long-caf-name"}
        _, links = readiness._expected_links(CONTEXT)
        search_name = context["SEARCH_SERVICE_RESOURCE_ID"].rsplit("/", 1)[1]
        context["SEARCH_SHARED_PRIVATE_LINKS"] = json.dumps([
            {"name": f"spl-{search_name}-blob-0" if link.group == "blob" else f"spl-application-search-abcdef-{link.group}-1",
             "groupId": link.group, "privateLinkResourceId": link.target} for link in links
        ])
        self.run_gate(MockArm(context), context=context)
        del context["SEARCH_SHARED_PRIVATE_LINKS"]
        with self.assertRaisesRegex(readiness.PrivateLinkReadinessError, "bounded"):
            readiness.ensure_native_blob_private_links(DEFINITIONS, context, self.credential)

    def test_valid_resource_groups_include_parentheses_and_unicode_without_target_reads(self):
        for group in ("prod(east)", "équipe(東京)_١", "İstanbul(Prod)", "_team", "x" * 90):
            with self.subTest(group=group):
                self.network.reset_mock()
                context = {
                    **CONTEXT,
                    **{
                        key: CONTEXT[key].replace("/resourceGroups/test/", f"/resourceGroups/{group}/")
                        for key in (
                            "SEARCH_SERVICE_RESOURCE_ID", "STORAGE_ACCOUNT_RESOURCE_ID",
                            "AI_FOUNDRY_ACCOUNT_RESOURCE_ID",
                        )
                    },
                }
                definitions = deepcopy(DEFINITIONS)
                definitions["knowledgeSources"][0]["azureBlobParameters"]["connectionString"] = (
                    f"ResourceId={context['STORAGE_ACCOUNT_RESOURCE_ID']}"
                )
                self.run_gate(MockArm(context), context=context, definitions=definitions)
                self.assertEqual(self.network.call_count, 4)
                self.assertTrue(all("/privateEndpointConnections" not in call.args[1] for call in self.network.call_args_list))

    def test_invalid_resource_group_segments_and_arm_paths_fail_before_auth_or_network(self):
        for group in (
            "bad/group", r"bad\\group", ".", "..", "trailing.", "space name",
            "bad%2Fgroup", "bad?query", "bad#fragment", "bad@host", "bad:443",
            "bad\nname", "bad\u200bname", "emoji😀", "bad²", "x" * 91,
        ):
            with self.subTest(group=group):
                context = {**CONTEXT, "SEARCH_SERVICE_RESOURCE_ID": SEARCH.replace(
                    "/resourceGroups/test/", f"/resourceGroups/{group}/",
                )}
                with self.assertRaises(readiness.PrivateLinkReadinessError):
                    readiness.ensure_native_blob_private_links(DEFINITIONS, context, self.credential)
        for resource_id in (
            f"https://untrusted.example{SEARCH}",
            SEARCH + "/extra", SEARCH + "?api-version=wrong", SEARCH + "#fragment",
            SEARCH.replace("/resourceGroups/test/", "/resourceGroups/test/../other/"),
        ):
            with self.subTest(resource_id=resource_id):
                with self.assertRaises(readiness.PrivateLinkReadinessError):
                    readiness.ensure_native_blob_private_links(
                        DEFINITIONS, {**CONTEXT, "SEARCH_SERVICE_RESOURCE_ID": resource_id}, self.credential,
                    )
        self.network.assert_not_called()
        self.credential.get_token.assert_not_called()

    def test_mocked_arm_readiness_precedes_source_creation_and_pending_stops_it(self):
        arm = MockArm()
        self.network.side_effect = arm.request
        with patch.object(setup, "call_search_api", return_value=True) as create:
            def checked_create(*args):
                self.assertEqual(self.network.call_count, 4)
                return True
            create.side_effect = checked_create
            self.assertTrue(setup.provision_knowledge_sources(DEFINITIONS, CONTEXT, self.credential, "https://test"))
            create.assert_called_once()
            create.reset_mock()
            self.network.side_effect = MockArm(approved=False).request
            with self.assertRaisesRegex(readiness.PrivateLinkReadinessError, "Administrator"):
                setup.provision_knowledge_sources(DEFINITIONS, CONTEXT, self.credential, "https://test")
            create.assert_not_called()

    def test_setup_readiness_failure_precedes_cleanup_and_search_mutation(self):
        with patch.object(setup, "ChainedTokenCredential", return_value=self.credential), patch.object(
            setup, "ensure_native_blob_private_links", side_effect=readiness.PrivateLinkReadinessError("blocked"),
        ), patch.object(setup, "prepare_index_updates") as prepare, patch.object(
            setup, "cleanup_knowledge_resources",
        ) as cleanup:
            with self.assertRaises(readiness.PrivateLinkReadinessError):
                setup.execute_setup(DEFINITIONS, CONTEXT)
            prepare.assert_not_called()
            cleanup.assert_not_called()

    def test_terminal_http_failure_and_redirect_not_swallowed(self):
        for status in (400, 409, 302):
            with self.subTest(status=status):
                arm = MockArm()
                arm.force_status = status
                with self.assertRaisesRegex(readiness.PrivateLinkReadinessError, f"HTTP {status}"):
                    self.run_gate(arm)

    def test_budget_expiration_during_authentication_stops_before_network(self):
        def credential_delay(*args):
            self.clock = 4
            return Mock(token="offline-token")
        self.credential.get_token.side_effect = credential_delay
        with self.assertRaisesRegex(readiness.PrivateLinkReadinessError, "deadline"):
            readiness.ensure_native_blob_private_links(
                DEFINITIONS, CONTEXT, self.credential, timeout_seconds=3, poll_seconds=1,
            )
        self.network.assert_not_called()

    def test_template_publishes_exact_names_targets_and_existing_label(self):
        template = (Path(__file__).resolve().parents[3] / "infra/main.bicep").read_text(encoding="utf-8")
        self.assertIn("var searchFoundrySharedPrivateLinkReadinessManifest = [for spl in searchFoundrySharedPrivateLinkResources:", template)
        self.assertIn("name: spl.name", template)
        self.assertIn("name: 'spl-${resourceNames.searchServiceName}-blob-0'", template)
        self.assertIn("value: string(searchSharedPrivateLinkReadinessManifest), label: appConfigLabel, contentType: 'application/json'", template)


if __name__ == "__main__":
    unittest.main()
