"""Pick up branch / commit / build URL from common CI environments."""

from __future__ import annotations

import os
from collections.abc import Mapping


def detect(env: Mapping[str, str] | None = None) -> dict[str, str]:
    e = os.environ if env is None else env
    g = lambda k: e.get(k, "").strip()  # noqa: E731

    if g("GITHUB_ACTIONS") == "true":
        branch = g("GITHUB_HEAD_REF") or g("GITHUB_REF_NAME")
        url = ""
        if g("GITHUB_SERVER_URL") and g("GITHUB_REPOSITORY") and g("GITHUB_RUN_ID"):
            url = f"{g('GITHUB_SERVER_URL')}/{g('GITHUB_REPOSITORY')}/actions/runs/{g('GITHUB_RUN_ID')}"
        return _clean(ci="GitHub Actions", branch=branch, commit=g("GITHUB_SHA"), build_url=url,
                      build=g("GITHUB_RUN_NUMBER"))
    if g("BITBUCKET_BUILD_NUMBER"):
        url = ""
        if g("BITBUCKET_GIT_HTTP_ORIGIN"):
            url = f"{g('BITBUCKET_GIT_HTTP_ORIGIN')}/pipelines/results/{g('BITBUCKET_BUILD_NUMBER')}"
        return _clean(ci="Bitbucket Pipelines", branch=g("BITBUCKET_BRANCH") or g("BITBUCKET_TAG"),
                      commit=g("BITBUCKET_COMMIT"), build_url=url, build=g("BITBUCKET_BUILD_NUMBER"))
    if g("GITLAB_CI") == "true":
        return _clean(ci="GitLab CI", branch=g("CI_COMMIT_REF_NAME"), commit=g("CI_COMMIT_SHA"),
                      build_url=g("CI_PIPELINE_URL") or g("CI_JOB_URL"), build=g("CI_PIPELINE_IID"))
    if g("JENKINS_URL"):
        return _clean(ci="Jenkins", branch=g("BRANCH_NAME") or g("GIT_BRANCH"), commit=g("GIT_COMMIT"),
                      build_url=g("BUILD_URL"), build=g("BUILD_NUMBER"))
    return {}


def _clean(**kw: str) -> dict[str, str]:
    return {k: v for k, v in kw.items() if v}
