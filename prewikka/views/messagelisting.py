# Copyright (C) 2004 Nicolas Delon <nicolas@prelude-ids.org>
# All Rights Reserved
#
# This file is part of the Prelude program.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2, or (at your option)
# any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; see the file COPYING.  If not, write to
# the Free Software Foundation, 675 Mass Ave, Cambridge, MA 02139, USA.


import time
import copy

from prewikka import view, User, utils


class _MyTime:
    def __init__(self, t=None):
        self._t = t or time.time()
        self._index = 5 # second index

    def __getitem__(self, key):
        try:
            self._index = [ "year", "month", "day", "hour", "min", "sec" ].index(key)
        except ValueError:
            raise KeyError(key)
        
        return self

    def round(self, unit):
        t = list(time.localtime(self._t))
        if unit != "sec":
            t[5] = 0
            if unit != "min":
                t[4] = 0
                if unit != "hour":
                    t[3] = 0
                    if unit != "day":
                        t[2] = 1
                        if unit != "month":
                            t[1] = 1
                            t[0] += 1
                        else:
                            t[1] += 1
                    else:
                        t[2] += 1
                else:
                    t[3] += 1
            else:
                t[4] += 1
        else:
            t[5] += 1
        self._t = time.mktime(t)                

    def __add__(self, value):
        t = time.localtime(self._t)
        t = list(t)
        t[self._index] += value
        t = time.mktime(t)
        return _MyTime(t)

    def __sub__(self, value):
        return self + (-value)

    def __str__(self):
        return utils.time_to_ymdhms(time.localtime(self._t))
    
    def __int__(self):
        return int(self._t)



class MessageListingParameters(view.Parameters):
    def register(self):
        self.optional("timeline_value", int, default=1)
        self.optional("timeline_unit", str, default="hour")
        self.optional("timeline_end", int)
        self.optional("offset", int, default=0)
        self.optional("limit", int, default=50)
        self.optional("timezone", str, "frontend_localtime")
        self.optional("idents", list, [])
        # submit with an image passes the x and y coordinate values
        # where the image was clicked
        self.optional("x", int)
        self.optional("y", int)
        
    def normalize(self):
        view.Parameters.normalize(self)
        
        for p1, p2 in [ ("timeline_value", "timeline_unit") ]:
            if self.has_key(p1) ^ self.has_key(p2):
                raise view.MissingParameterError(self.has_key(p1) and p1 or p2)
            
        if not self["timezone"] in ("frontend_localtime", "sensor_localtime", "utc"):
            raise view.InvalidValueError("timezone", self["timezone"])
        
        idents = [ ]
        for ident in self["idents"]:
            try:
                analyzerid, message_ident = map(lambda x: long(x), ident.split(":"))
            except ValueError:
                raise view.InvalidParameterValueError("idents", self["idents"])
            
            idents.append((analyzerid, message_ident))

        self["idents"] = idents

        # remove the bulshit
        try:
            del self["x"]
            del self["y"]
        except KeyError:
            pass



class AlertListingParameters(MessageListingParameters):
    allow_extra_parameters = True

    def register(self):
        MessageListingParameters.register(self)
        self.optional("filter", str)
        self.optional("alert.classification.text", list)
        self.optional("alert.analyzer.name", list)

    def normalize(self):
        MessageListingParameters.normalize(self)

        for direction in "source", "target":
            self["alert.%s.node" % direction] = [ ]
            for parameter, value in self.items():
                idx = parameter.find("%s_type_" % direction)
                if idx == -1:
                    continue
                num = parameter.replace("%s_type_" % direction, "", 1)

                if self.has_key("alert.%s.node_%s" % (direction, num)):
                    self["alert.%s.node" % direction].append((value,
                                                              self["alert.%s.node_%s" % (direction, num)]))



class HeartbeatListingParameters(MessageListingParameters):
    pass



class SensorAlertListingParameters(AlertListingParameters):
    def register(self):
        AlertListingParameters.register(self)
        self.mandatory("analyzerid", long)



class SensorHeartbeatListingParameters(HeartbeatListingParameters):
    def register(self):
        HeartbeatListingParameters.register(self)
        self.mandatory("analyzerid", long)



class MessageListing:
    def _setInlineFilter(self):
        if self.parameters.has_key("inline_filter_object"):
            self.dataset["active_inline_filter"] = self.inline_filters[self.parameters["inline_filter_object"]]
        else:
            self.dataset["active_inline_filter"] = ""
        self.dataset["remove_active_inline_filter"] = utils.create_link(self.view_name,
                                                                        self.parameters - \
                                                                        [ "inline_filter_object",
                                                                          "inline_filter_value",
                                                                          "offset"])

    def _setTimelineNext(self, next):
        parameters = self.parameters - [ "offset" ] + { "timeline_end": int(next) }
        self.dataset["timeline.next"] = utils.create_link(self.view_name, parameters)

    def _setTimelinePrev(self, prev):
        parameters = self.parameters - [ "offset" ] + { "timeline_end": int(prev) }
        self.dataset["timeline.prev"] = utils.create_link(self.view_name, parameters)
        
    def _getTimelineRange(self):
        if self.parameters.has_key("timeline_end"):
            end = _MyTime(self.parameters["timeline_end"])
        else:
            end = _MyTime()
            if not self.parameters["timeline_unit"] in ("min", "hour"):
                end.round(self.parameters["timeline_unit"])
        
        start = end[self.parameters["timeline_unit"]] - self.parameters["timeline_value"]

        return start, end
        
    def _setTimeline(self, start, end):
        self.dataset["timeline.current"] = utils.create_link(self.view_name, self.parameters - ["timeline_end"])

        self.dataset["timeline.value"] = self.parameters["timeline_value"]
        self.dataset["timeline.%s_selected" % self.parameters["timeline_unit"]] = "selected"

        if self.parameters["timezone"] == "utc":
            self.dataset["timeline.start"] = utils.time_to_ymdhms(time.gmtime(int(start)))
            self.dataset["timeline.end"] = utils.time_to_ymdhms(time.gmtime(int(end)))
            self.dataset["timeline.range_timezone"] = "UTC"
        else:
            self.dataset["timeline.start"] = utils.time_to_ymdhms(time.localtime(int(start)))
            self.dataset["timeline.end"] = utils.time_to_ymdhms(time.localtime(int(end)))
            self.dataset["timeline.range_timezone"] = "%+.2d:%.2d" % utils.get_gmt_offset()

        if not self.parameters.has_key("timeline_end") and self.parameters["timeline_unit"] in ("min", "hour"):
            tmp = copy.copy(end)
            tmp.round(self.parameters["timeline_unit"])
            tmp = tmp[self.parameters["timeline_unit"]] - 1
            self._setTimelineNext(tmp[self.parameters["timeline_unit"]] + self.parameters["timeline_value"])
            self._setTimelinePrev(tmp[self.parameters["timeline_unit"]] - (self.parameters["timeline_value"] - 1))
        else:
            self._setTimelineNext(end[self.parameters["timeline_unit"]] + self.parameters["timeline_value"])
            self._setTimelinePrev(end[self.parameters["timeline_unit"]] - self.parameters["timeline_value"])

    def _setNavPrev(self, offset):
        if offset:
            self.dataset["nav.first"] = utils.create_link(self.view_name, self.parameters - [ "offset" ])
            self.dataset["nav.prev"] = utils.create_link(self.view_name,
                                                         self.parameters +
                                                         { "offset": offset - self.parameters["limit"] })
        else:
            self.dataset["nav.prev"] = None
            
    def _setNavNext(self, offset, count):
        if count > offset + self.parameters["limit"]:
            offset = offset + self.parameters["limit"]
            self.dataset["nav.next"] = utils.create_link(self.view_name, self.parameters + { "offset": offset })
            offset = count - ((count % self.parameters["limit"]) or self.parameters["limit"])
            self.dataset["nav.last"] = utils.create_link(self.view_name, self.parameters + { "offset": offset })
        else:
            self.dataset["nav.next"] = None

    def _createTimeField(self, t, timezone):
        if t:
            if timezone == "utc":
                t = time.gmtime(t)
            elif timezone == "sensor_localtime":
                t = time.gmtime(int(t) + t.gmt_offset)
            else: # timezone == "frontend_localtime"
                t = time.localtime(t)
            
            current = time.localtime()
        
            if t[:3] == current[:3]: # message time is today
                t = utils.time_to_hms(t)
            else:
                t = utils.time_to_ymdhms(t)
        else:
            t = "n/a"

        return { "value": t }

    def _createInlineFilteredField(self, object, value):
        if not value:
            return { "value": "n/a", "inline_filter": None }

        parameters = self.parameters + { object: value }

        return { "value": value, "inline_filter": utils.create_link(self.view_name, parameters) }

    def _createHostField(self, object, value):
        field = self._createInlineFilteredField(object, value)
        field["host_commands"] = [ ]
        if not value:
            return field

        for command in "whois", "traceroute":
            if self.env.host_commands.has_key(command):
                field["host_commands"].append((command.capitalize(),
                                               utils.create_link(command,
                                                                 { "origin": self.view_name, "host": value })))

        return field
    
    def _createMessageLink(self, message, view):
        return utils.create_link(view, { "origin": self.view_name,
                                         "analyzerid": message.getAnalyzerID(),
                                         "ident": message.getMessageID() })

    def _setMessages(self, criteria):
        self.dataset["messages"] = [ ]

        objects = [ self.root + ".analyzer.analyzerid",
                    self.root + ".messageid",
                    self.root + ".create_time/order_desc" ]
        
        for analyzerid, ident, ctime in self.env.prelude.getValues(objects,
                                                                   criteria=criteria,
                                                                   distinct=1,
                                                                   limit=self.parameters["limit"],
                                                                   offset=self.parameters["offset"]):
            src = self._fetchMessage(analyzerid, ident)
            dst = {
                "summary": self._createMessageLink(src, self.summary_view),
                "details": self._createMessageLink(src, self.details_view),
                "analyzerid": { "value": src.getAnalyzerID() },
                "ident": { "value": src.getMessageID() }
                }
            self._setMessage(dst, src)
            self.dataset["messages"].append(dst)

    def _setTimezone(self):
        for timezone in "utc", "sensor_localtime", "frontend_localtime":
            if timezone == self.parameters["timezone"]:
                self.dataset["timeline.%s_selected" % timezone] = "selected"
            else:
                self.dataset["timeline.%s_selected" % timezone] = ""

    def _getInlineFilter(self, name):
        return name, self.parameters.get(name)

    def _deleteMessages(self):
        if len(self.parameters["idents"]) == 0:
            return
        
        if not self.user.has(User.PERM_IDMEF_ALTER):
            raise User.PermissionDeniedError(user.login, self.current_view)

        for analyzerid, messageid in self.parameters["idents"]:
            self._deleteMessage(analyzerid, messageid)

    def render(self, criteria=[]):
        self._deleteMessages()
        
        start, end = self._getTimelineRange()
        
        criteria.append(self.time_criteria_format % (str(start), str(end)))
        criteria = " && ".join(criteria)

        self._setInlineFilter()
        self._setTimeline(start, end)
        self._setNavPrev(self.parameters["offset"])

        count = self._countMessages(criteria)

        self._setMessages(criteria)

        self.dataset["current_view"] = self.view_name
        self.dataset["nav.from"] = self.parameters["offset"] + 1
        self.dataset["nav.to"] = self.parameters["offset"] + len(self.dataset["messages"])
        self.dataset["limit"] = self.parameters["limit"]
        self.dataset["total"] = count

        self._setNavNext(self.parameters["offset"], count)
        self._setTimezone()



class AlertListing(MessageListing, view.View):
    view_name = "alert_listing"
    view_parameters = AlertListingParameters
    view_permissions = [ User.PERM_IDMEF_VIEW ]
    view_template = "AlertListing"

    root = "alert"
    messageid_object = "alert.messageid"
    analyzerid_object = "alert.analyzer.analyzerid"
    summary_view = "alert_summary"
    details_view = "alert_details"
    time_criteria_format = "alert.create_time >= '%s' && alert.create_time < '%s'"
    message_criteria_format = "alert.analyzer.analyzerid == '%d' && alert.messageid == '%d'"

    def _countMessages(self, criteria):
        return self.env.prelude.countAlerts(criteria)

    def _fetchMessage(self, analyzerid, ident):
        return self.env.prelude.getAlert(analyzerid, ident)

    def _setMessageSource(self, dst, src):
        dst["sinterface"] = { "value": src["alert.source(0).interface"] }
        dst["suser_name"] = { "value": src["alert.source(0).user.user_id(0).name"] }
        dst["suser_uid"] = { "value": src["alert.source(0).user.user_id(0).number"] }
        dst["sprocess_name"] = { "value": src["alert.source(0).process.name"] }
        dst["sprocess_pid"] = { "value": src["alert.source(0).process.pid"] }

        if src["alert.source(0).service.port"]:
            dst["sservice"] = { "value": src["alert.source(0).service.port"] }
            dst["sservice_extra"] = { "value": src["alert.source(0).service.name"] }
        else:
            dst["sservice"] = { "value": src["alert.source(0).service.name"] }
        
        if src["alert.source(0).node.address(0).address"]:
            dst["source"] = self._createHostField("alert.source.node.address.address",
                                                  src["alert.source(0).node.address(0).address"])
            dst["source_extra"] = { "value": src["alert.source(0).node.name"] }
        else:
            dst["source"] = self._createHostField("alert.source.node.name", src["alert.source(0).node.name"])
            dst["source_extra"] = { "value": None }
        
    def _setMessageTarget(self, dst, src):
        dst["tinterface"] = { "value": src["alert.target(0).interface"] }
        dst["tuser_name"] = { "value": src["alert.target(0).user.user_id(0).name"] }
        dst["tuser_uid"] = { "value": src["alert.target(0).user.user_id(0).number"] }
        dst["tprocess_name"] = { "value": src["alert.target(0).process.name"] }
        dst["tprocess_pid"] = { "value": src["alert.target(0).process.pid"] }

        if src["alert.target(0).service.port"]:
            dst["tservice"] = { "value": src["alert.target(0).service.port"] }
            dst["tservice_extra"] = { "value": src["alert.target(0).service.name"] }
        else:
            dst["tservice"] = { "value": src["alert.target(0).service.name"] }
            dst["tservice_extra"] = { "value": None }
        
        if src["alert.target(0).node.address(0).address"]:
            dst["target"] = self._createHostField("alert.target.node.address.address",
                                                  src["alert.target(0).node.address(0).address"])
            dst["target_extra"] = { "value": src["alert.target(0).node.name"] }
        else:
            dst["target"] = self._createHostField("alert.target.node.name", src["alert.target(0).node.name"])
            dst["target_extra"] = { "value": None }
        
    def _setMessageSensor(self, dst, src):
        dst["sensor_node_name"] = { "value": alert["alert.analyzer.node.name"] }
        dst["sensor"] = self._createInlineFilteredField("alert.analyzer.name", src["alert.analyzer.name"])

    def _setMessageClassification(self, dst, src):
        urls = [ ]
        cnt = 0

        while True:
            origin = src["alert.classification.reference(%d).origin" % cnt]
            if origin is None:
                break
            
            name = src["alert.classification.reference(%d).name" % cnt]
            if not name:
                continue

            url = src["alert.classification.reference(%d).url" % cnt]
            if not url:
                continue
            
            urls.append("<a href='%s'>%s:%s</a>" % (url, origin, name))

            cnt += 1

        if urls:
            dst["classification_references"] = "(" + ", ".join(urls) + ")"
        else:
            dst["classification_references"] = ""

        dst["classification"] = self._createInlineFilteredField("alert.classification.text",
                                                                src["alert.classification.text"])

    def _setMessageSensor(self, dst, src):
        def get_analyzer_names(alert, root):
            analyzerid = alert[root + ".analyzerid"]
            if analyzerid != None:
                return [ alert[root + ".name"] ] + get_analyzer_names(alert, root + ".analyzer")
            return [ ]

        analyzers = get_analyzer_names(src, "alert.analyzer")

        dst["sensor"] = self._createInlineFilteredField("alert.analyzer.name", analyzers[0])
        dst["sensor"]["value"] = "/".join(analyzers[:-1])

        dst["sensor_node_name"] = { "value": src["alert.analyzer.node.name"] }
        
    def _setMessage(self, dst, src):
        dst["severity"] = { "value": src.get("alert.assessment.impact.severity", "low") }
        dst["completion"] = { "value": src["alert.assessment.impact.completion"] }
        dst["time"] = self._createTimeField(src["alert.create_time"], self.parameters["timezone"])
        self._setMessageSource(dst, src)
        self._setMessageTarget(dst, src)
        self._setMessageSensor(dst, src)
        self._setMessageClassification(dst, src)
        self._setMessageSensor(dst, src)

    def _getFilters(self, storage, login):
        return storage.getAlertFilters(login)

    def _getFilter(self, storage, login, name):
        return storage.getAlertFilter(login, name)

    def _getInlineFilterObject(self, filter):
        try:
            return self.parameters({"alert.source.node": "source_type",
                                    "alert.target.node": "target_type"}[filter])
        except:
            return filter

    def _deleteMessage(self, analyzerid, messageid):
        self.env.prelude.deleteAlert(analyzerid, messageid)
        
    def render(self):
        criteria = [ ]

        if self.parameters.has_key("filter"):
            filter = self.env.storage.getAlertFilter(self.user.login, self.parameters["filter"])
            criteria.append("(%s)" % str(filter))

        if self.parameters.has_key("alert.classification.text") and \
           len(self.parameters["alert.classification.text"]) > 0:
            criteria.append(" || ".join(map(lambda x: "alert.classification.text substr '%s'" % x,
                                            self.parameters["alert.classification.text"])))
            self.dataset["alert.classification.text"] = self.parameters["alert.classification.text"]
            self.dataset["classification_filtered"] = True
        else:
            self.dataset["alert.classification.text"] = [ "" ]
            self.dataset["classification_filtered"] = False

        for direction in "source", "target":
            if self.parameters["alert.%s.node" % direction]:
                criteria.append(" || ".join(map(lambda (o,v): "%s substr '%s'" % (o, v),
                                                self.parameters["alert.%s.node" % direction])))
                self.dataset["alert.%s.node" % direction] = self.parameters["alert.%s.node" % direction]
                self.dataset["%s_filtered" % direction] = True
            else:
                self.dataset["alert.%s.node" % direction] = [ ("alert.%s.node.address.address" % direction, "") ]
                self.dataset["%s_filtered" % direction] = False

        if self.parameters.has_key("alert.analyzer.name") and \
           len(self.parameters["alert.analyzer.name"]) > 0:
            criteria.append(" || ".join(map(lambda x: "alert.analyzer.name substr '%s'" % x,
                                            self.parameters["alert.analyzer.name"])))
            self.dataset["alert.analyzer.name"] = self.parameters["alert.analyzer.name"]
            self.dataset["analyzer_filtered"] = True
        else:
            self.dataset["alert.analyzer.name"] = [ "" ]
            self.dataset["analyzer_filtered"] = False

        MessageListing.render(self, criteria)
        
        self.dataset["filters"] = self.env.storage.getAlertFilters(self.user.login)
        self.dataset["current_filter"] = self.parameters.get("filter", "")



class HeartbeatListing(MessageListing, view.View):
    view_name = "heartbeat_listing"
    view_parameters = HeartbeatListingParameters
    view_permissions = [ User.PERM_IDMEF_VIEW ]
    view_template = "HeartbeatListing"

    root = "heartbeat"
    filters = { }
    summary_view = "heartbeat_summary"
    details_view = "heartbeat_details"
    time_criteria_format = "heartbeat.create_time >= '%s' && heartbeat.create_time < '%s'"
    message_criteria_format = "heartbeat.analyzer.analyzerid == '%d' && heartbeat.messageid == '%d'"

    def _countMessages(self, criteria):
        return self.env.prelude.countHeartbeats(criteria)

    def _fetchMessage(self, analyzerid, ident):
        return self.env.prelude.getHeartbeat(analyzerid, ident)

    def _setMessage(self, dst, src):
        dst["agent"] = self._createInlineFilteredField("heartbeat.analyzer.name",
                                                       src["heartbeat.analyzer.name"])
        dst["model"] = self._createInlineFilteredField("heartbeat.analyzer.model",
                                                       src["heartbeat.analyzer.model"])
        dst["node_name"] = self._createInlineFilteredField("heartbeat.analyzer.node.name",
                                                           src["heartbeat.analyzer.node.name"])
        dst["node_address"] = self._createHostField("heartbeat.analyzer.node.address.address",
                                                    src["heartbeat.analyzer.node.address(0).address"])
        dst["time"] = self._createTimeField(src["heartbeat.create_time"], self.parameters["timezone"])

    def _deleteMessage(self, analyzerid, messageid):
        self.env.prelude.deleteHeartbeat(analyzerid, messageid)



class SensorAlertListing(AlertListing, view.View):
    view_name = "sensor_alert_listing"
    view_parameters = SensorAlertListingParameters
    view_permissions = [ User.PERM_IDMEF_VIEW ]
    view_template = "SensorAlertListing"

    def _adjustCriteria(self, criteria):
        criteria.append("alert.analyzer.analyzerid == %d" % self.parameters["analyzerid"])

    def render(self):
        AlertListing.render(self)
        self.dataset["analyzer"] = self.env.prelude.getAnalyzer(self.parameters["analyzerid"])



class SensorHeartbeatListing(HeartbeatListing, view.View):
    view_name = "sensor_heartbeat_listing"
    view_parameters = SensorHeartbeatListingParameters
    view_permissions = [ User.PERM_IDMEF_VIEW ]
    view_template = "SensorHeartbeatListing"

    def _adjustCriteria(self, criteria):
        criteria.append("heartbeat.analyzer.analyzerid == %d" % self.parameters["analyzerid"])

    def render(self):
        HeartbeatListing.render(self)
        self.dataset["analyzer"] = self.env.prelude.getAnalyzer(self.parameters["analyzerid"])
