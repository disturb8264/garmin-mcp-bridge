import unittest
from contextlib import asynccontextmanager
from types import SimpleNamespace

from mcp import types

from gateway.app import Registry, Upstream


class UIResourceTests(unittest.IsolatedAsyncioTestCase):
    async def test_only_allowed_tool_ui_resource_is_exposed(self):
        upstream = Upstream('route', 'http://127.0.0.1:18768/mcp', 'x' * 32,
                            frozenset({'render_route'}))
        registry = Registry([upstream])
        uri = 'ui://route/viewer.html'
        hidden_uri = 'ui://route/hidden.html'
        tools = [
            types.Tool(name='render_route', inputSchema={'type': 'object'},
                       _meta={'ui': {'resourceUri': uri}}),
            types.Tool(name='hidden', inputSchema={'type': 'object'},
                       _meta={'ui': {'resourceUri': hidden_uri}}),
        ]
        resources = [
            types.Resource(uri=uri, name='viewer', mimeType='text/html;profile=mcp-app'),
            types.Resource(uri=hidden_uri, name='hidden', mimeType='text/html;profile=mcp-app'),
        ]

        class Session:
            async def list_tools(self, params=None):
                return SimpleNamespace(tools=tools, next_cursor=None)

            async def list_resources(self, params=None):
                return SimpleNamespace(resources=resources, next_cursor=None)

            async def read_resource(self, requested_uri):
                return types.ReadResourceResult(contents=[
                    types.TextResourceContents(uri=requested_uri, mimeType='text/html;profile=mcp-app',
                                               text='<html>viewer</html>')])

        @asynccontextmanager
        async def session(_upstream):
            yield Session()

        registry.session = session
        await registry.refresh_one(upstream)
        listed_tools = await registry.list_tools(None, None)
        self.assertEqual([tool.name for tool in listed_tools.tools], ['route_render_route'])
        self.assertEqual(listed_tools.tools[0].meta['ui']['resourceUri'], uri)
        listed_resources = await registry.list_resources(None, None)
        self.assertEqual([str(resource.uri) for resource in listed_resources.resources], [uri])
        read = await registry.read_resource(None, types.ReadResourceRequestParams(uri=uri))
        self.assertEqual(read.contents[0].text, '<html>viewer</html>')
        with self.assertRaises(ValueError):
            await registry.read_resource(None, types.ReadResourceRequestParams(uri=hidden_uri))


if __name__ == '__main__':
    unittest.main()
