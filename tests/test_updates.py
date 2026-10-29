import json
from threading import Event
import time
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError

from lado.updates import API_URL, MAX_RESPONSE, INTERVAL, UpdateService, fetch_releases, find_update, trusted_download, version_key


def release(version, arch="arm64", **extra):
    name = f"Lado-{version}-macOS-{arch}.dmg"
    return {"tag_name": "v"+version, "draft": False, "assets": [{
        "name": name, "state": "uploaded",
        "browser_download_url": "https://github.com/sirdimitry/Lado/releases/download/v"+version+"/"+name}], **extra}


class ReleaseSelectionTests(unittest.TestCase):
    def test_numeric_versions_not_strings(self):
        result = find_update([release("0.1.9"), release("0.1.10")], "0.1.0", "arm64")
        self.assertEqual(result.version, "0.1.10")

    def test_no_downgrade_or_same_version(self):
        self.assertIsNone(find_update([release("0.1.0"), release("0.0.9")], "0.1.0", "arm64"))

    def test_rc_before_final(self):
        self.assertLess(version_key("1.0.0-rc.2"), version_key("1.0.0"))
        self.assertLess(version_key("1.0.0-beta1"), version_key("1.0.0-rc1"))

    def test_unpublished_and_missing_installers(self):
        self.assertIsNone(find_update([release("0.2.0", draft=True), {"tag_name":"v0.3.0","assets":[]}], "0.1.0", "arm64"))

    def test_published_preview_is_supported(self):
        self.assertEqual(find_update([release("0.2.0", prerelease=True)], "0.1.0", "arm64").version, "0.2.0")

    def test_architecture_match_and_universal_fallback(self):
        self.assertIsNone(find_update([release("0.2.0", "x86_64")], "0.1.0", "arm64"))
        result = find_update([release("0.2.0","universal2"),release("0.2.0","arm64")], "0.1.0", "arm64")
        self.assertIn("arm64", result.filename)
        result = find_update([release("0.2.0","universal2")], "0.1.0", "x86_64")
        self.assertIn("universal2", result.filename)

    def test_malformed_versions_and_payloads_are_ignored(self):
        for value in (None, {}, "latest", "v2", "1.2.3.4", "1.2.3<script>"):
            self.assertIsNone(version_key(value))
        for payload in (None, {}, "text", [None,{},release("0.2.0", assets=None)]):
            self.assertIsNone(find_update(payload, "0.1.0", "arm64"))

    def test_asset_must_be_uploaded(self):
        data = release("0.2.0")
        data["assets"][0]["state"] = "new"
        self.assertIsNone(find_update([data],"0.1.0","arm64"))

    def test_asset_version_must_match_release_to_avoid_downgrade(self):
        data=release("0.0.9")
        data["tag_name"]="v0.2.0"
        self.assertIsNone(find_update([data],"0.1.0","arm64"))

    def test_only_our_https_release_downloads(self):
        name = "Lado-0.2.0-macOS-arm64.dmg"
        good = "https://github.com/sirdimitry/Lado/releases/download/v0.2.0/"+name
        self.assertTrue(trusted_download(good,name))
        for bad in (good.replace("https:","http:"), good.replace("github.com","github.com.evil.test"),
                    good.replace("sirdimitry/Lado", "other/Lado"), good.replace("github.com/", "user@github.com/"),
                    good+"?redirect=elsewhere", good+"#fragment", good.replace("v0.2.0/","../"),
                    good.replace("v0.2.0/","%2e%2e/"), good.replace(".dmg",".exe")):
            self.assertFalse(trusted_download(bad,name), bad)


class FetchTests(unittest.TestCase):
    def response(self, data):
        response = Mock()
        response.read.return_value = data
        response.headers = {"ETag": '"public-release-etag"'}
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        return response

    def test_request_has_fixed_url_no_auth_and_bounded_read(self):
        response = self.response(json.dumps([release("0.2.0")]).encode())
        opener = Mock()
        opener.open.return_value = response
        with patch("lado.updates.build_opener", return_value=opener):
            data, tag, status = fetch_releases('"old"')
        request = opener.open.call_args.args[0]
        self.assertEqual(request.full_url,API_URL)
        self.assertEqual(request.get_method(),"GET")
        self.assertIsNone(request.data)
        self.assertFalse(request.has_header("Authorization"))
        self.assertEqual(request.get_header("If-none-match"),'"old"')
        response.read.assert_called_once_with(MAX_RESPONSE+1)
        self.assertEqual((status,tag),("ok",'"public-release-etag"'))

    def test_bad_json_and_oversize(self):
        for value in (b"not json", b"{}", b"x"*(MAX_RESPONSE+1)):
            opener=Mock()
            opener.open.return_value=self.response(value)
            with patch("lado.updates.build_opener",return_value=opener):
                self.assertEqual(fetch_releases()[2],"unavailable")

    def test_offline_404_and_304(self):
        for error, status in ((URLError("offline"),"unavailable"),
                              (HTTPError(API_URL,404,"none",{},None),"ok"),
                              (HTTPError(API_URL,304,"cached",{},None),"not_modified"),
                              (HTTPError(API_URL,403,"rate limited",{},None),"unavailable")):
            opener=Mock()
            opener.open.side_effect=error
            with patch("lado.updates.build_opener",return_value=opener):
                self.assertEqual(fetch_releases()[2],status)


class ServiceTests(unittest.TestCase):
    def result(self, service):
        end=time.monotonic()+1
        while time.monotonic()<end:
            result=service.poll()
            if result:
                return result
            time.sleep(.002)
        self.fail("background check did not finish")

    def test_startup_delay_hourly_schedule_and_manual_flag(self):
        clock=[0]
        service=UpdateService("0.1.0","arm64", fetcher=lambda _: ([release("0.2.0")],None,"ok"), clock=lambda:clock[0])
        self.assertFalse(service.due())
        clock[0]=10
        self.assertTrue(service.due())
        service.check(manual=True)
        result=self.result(service)
        self.assertTrue(result.manual)
        self.assertEqual(result.update.version,"0.2.0")
        self.assertEqual(service.next_check,10+INTERVAL)

    def test_no_overlapping_workers(self):
        gate=Event()
        def fetch(_):
            gate.wait(1)
            return [],None,"ok"
        service=UpdateService("0.1.0",fetcher=fetch)
        self.assertTrue(service.check())
        self.assertFalse(service.check())
        gate.set()
        self.assertEqual(self.result(service).status,"ok")

    def test_unavailable_is_a_quiet_result(self):
        service=UpdateService("0.1.0",fetcher=lambda _: (None,None,"unavailable"))
        service.check()
        result=self.result(service)
        self.assertEqual(result.status,"unavailable")
        self.assertFalse(result.manual)
        self.assertIsNone(result.update)
