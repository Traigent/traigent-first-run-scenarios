# Disabled image parser

SPDX-License-Identifier: Apache-2.0

This Traigent-authored package is an intentional, fail-closed replacement for
the unused `image-size` transitive dependency in the PowerPoint build graph.
The presentation renders native text and shapes and supports no images. If
build tooling ever tries to load this module, it throws immediately instead of
parsing image bytes.

The package contains no parser, file reader, network client, or dependency. It
must remain a development-only build guard and must never be emitted into the
customer bundle.
