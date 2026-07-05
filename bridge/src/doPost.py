def doPost(request, session):
	return mcp_bridge_lib.handle(request)
