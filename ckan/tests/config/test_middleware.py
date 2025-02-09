# encoding: utf-8

import flask
import mock
import pytest
import wsgiref
from flask import Blueprint

import ckan.lib.helpers as h
import ckan.model as model
import ckan.plugins as p
import ckan.tests.factories as factories
from ckan.common import config, _
from ckan.config.middleware import AskAppDispatcherMiddleware
from ckan.config.middleware.flask_app import CKANFlask
from ckan.config.middleware.pylons_app import CKANPylonsApp


_test_controller = u"ckan.tests.config.test_middleware:MockPylonsController"


class MockRoutingPlugin(p.SingletonPlugin):

    p.implements(p.IRoutes)
    p.implements(p.IBlueprint)

    controller = _test_controller

    def before_map(self, _map):

        _map.connect(
            u"/from_pylons_extension_before_map",
            controller=self.controller,
            action=u"view",
        )

        _map.connect(
            u"/from_pylons_extension_before_map_post_only",
            controller=self.controller,
            action=u"view",
            conditions={u"method": u"POST"},
        )
        # This one conflicts with an extension Flask route
        _map.connect(
            u"/pylons_and_flask", controller=self.controller, action=u"view"
        )

        # This one conflicts with a core Flask route
        _map.connect(u"/about", controller=self.controller, action=u"view")

        _map.connect(
            u"/pylons_route_flask_url_for",
            controller=self.controller,
            action=u"test_flask_url_for",
        )
        _map.connect(
            u"/pylons_translated",
            controller=self.controller,
            action=u"test_translation",
        )

        return _map

    def after_map(self, _map):

        _map.connect(
            u"/from_pylons_extension_after_map",
            controller=self.controller,
            action=u"view",
        )

        return _map

    def get_blueprint(self):
        # Create Blueprint for plugin
        blueprint = Blueprint(self.name, self.__module__)

        blueprint.add_url_rule(
            u"/simple_flask", u"flask_plugin_view", flask_plugin_view
        )

        blueprint.add_url_rule(
            u"/flask_route_pylons_url_for",
            u"flask_route_pylons_url_for",
            flask_plugin_view_url_for,
        )
        blueprint.add_url_rule(
            u"/flask_translated", u"flask_translated", flask_translated_view
        )

        return blueprint


def flask_plugin_view():
    return u"Hello World, this is served from a Flask extension"


def flask_plugin_view_url_for():
    url = h.url_for(controller=_test_controller, action=u"view")
    return u"This URL was generated by Pylons: {0}".format(url)


def flask_translated_view():
    return _(u"Dataset")


class MockPylonsController(p.toolkit.BaseController):
    def view(self):
        return u"Hello World, this is served from a Pylons extension"

    def test_flask_url_for(self):
        url = h.url_for(u"api.get_api", ver=3)
        return u"This URL was generated by Flask: {0}".format(url)

    def test_translation(self):
        return _(u"Groups")


@pytest.fixture
def patched_app(app):
    flask_app = app.flask_app

    def test_view():
        return u"This was served from Flask"

    # This endpoint is defined both in Flask and in Pylons core
    flask_app.add_url_rule(
        u"/flask_core", view_func=test_view, endpoint=u"flask_core.index"
    )

    # This endpoint is defined both in Flask and a Pylons extension
    flask_app.add_url_rule(
        u"/pylons_and_flask",
        view_func=test_view,
        endpoint=u"pylons_and_flask.index",
    )
    return app


def test_ask_around_pylons_core_route_get(patched_app):
    environ = {u"PATH_INFO": u"/tag", u"REQUEST_METHOD": u"GET"}
    wsgiref.util.setup_testing_defaults(environ)

    answers = patched_app.app.ask_around(environ)

    assert answers == [(False, u"flask_app"), (True, u"pylons_app", u"core")]


def test_ask_around_pylons_core_route_post(patched_app):
    environ = {u"PATH_INFO": u"/tag", u"REQUEST_METHOD": u"POST"}
    wsgiref.util.setup_testing_defaults(environ)

    answers = patched_app.app.ask_around(environ)

    assert answers == [(False, u"flask_app"), (True, u"pylons_app", u"core")]


def test_flask_core_route_is_served_by_flask(patched_app):
    res = patched_app.get(u"/")

    assert res.environ[u"ckan.app"] == u"flask_app"


def test_flask_core_and_pylons_core_route_is_served_by_flask(patched_app):
    """
    This should never happen in core, but just in case
    """
    res = patched_app.get(u"/flask_core")

    assert res.environ[u"ckan.app"] == u"flask_app"
    assert res.body == u"This was served from Flask"


@pytest.mark.ckan_config(u"ckan.plugins", u"test_routing_plugin")
class TestMiddlewareWithRoutingPlugin:
    def test_ask_around_pylons_extension_route_get_before_map(
        self, patched_app
    ):
        environ = {
            u"PATH_INFO": u"/from_pylons_extension_before_map",
            u"REQUEST_METHOD": u"GET",
        }
        wsgiref.util.setup_testing_defaults(environ)

        answers = patched_app.app.ask_around(environ)

        assert answers == [
            (False, u"flask_app"),
            (True, u"pylons_app", u"extension"),
        ]

    def test_ask_around_pylons_extension_route_post(self, patched_app):
        environ = {
            u"PATH_INFO": u"/from_pylons_extension_before_map_post_only",
            u"REQUEST_METHOD": u"POST",
        }
        wsgiref.util.setup_testing_defaults(environ)

        answers = patched_app.app.ask_around(environ)

        assert answers == [
            (False, u"flask_app"),
            (True, u"pylons_app", u"extension"),
        ]

    def test_ask_around_pylons_extension_route_post_using_get(
        self, patched_app
    ):
        environ = {
            u"PATH_INFO": u"/from_pylons_extension_before_map_post_only",
            u"REQUEST_METHOD": u"GET",
        }
        wsgiref.util.setup_testing_defaults(environ)

        answers = patched_app.app.ask_around(environ)

        # We are going to get an answer from Pylons, but just because it will
        # match the catch-all template route, hence the `core` origin.
        assert answers == [
            (False, u"flask_app"),
            (True, u"pylons_app", u"core"),
        ]

    def test_ask_around_pylons_extension_route_get_after_map(
        self, patched_app
    ):
        environ = {
            u"PATH_INFO": u"/from_pylons_extension_after_map",
            u"REQUEST_METHOD": u"GET",
        }
        wsgiref.util.setup_testing_defaults(environ)

        answers = patched_app.app.ask_around(environ)

        assert answers == [
            (False, u"flask_app"),
            (True, u"pylons_app", u"extension"),
        ]

    def test_flask_extension_route_is_served_by_flask(self, patched_app):
        res = patched_app.get(u"/simple_flask")
        assert res.environ[u"ckan.app"] == u"flask_app"

    def test_pylons_extension_route_is_served_by_pylons(self, patched_app):

        res = patched_app.get(u"/from_pylons_extension_before_map")

        assert res.environ[u"ckan.app"] == u"pylons_app"
        assert (
            res.body == u"Hello World, this is served from a Pylons extension"
        )

    @pytest.mark.usefixtures(u"clean_db")
    def test_user_objects_in_g_normal_user(self, app):
        """
        A normal logged in user request will have expected user objects added
        to request.
        """
        username = factories.User()[u"name"]
        test_user_obj = model.User.by_name(username)

        with app.flask_app.app_context():
            app.get(
                u"/simple_flask",
                extra_environ={u"REMOTE_USER": username.encode(u"ascii")},
            )
            assert flask.g.user == username
            assert flask.g.userobj == test_user_obj
            assert flask.g.author == username
            assert flask.g.remote_addr == u"Unknown IP Address"

    @pytest.mark.usefixtures(u"clean_db")
    def test_user_objects_in_g_anon_user(self, app):
        """
        An anon user request will have expected user objects added to request.
        """
        with app.flask_app.app_context():
            app.get(u"/simple_flask", extra_environ={u"REMOTE_USER": str(u"")})
            assert flask.g.user == u""
            assert flask.g.userobj is None
            assert flask.g.author == u"Unknown IP Address"
            assert flask.g.remote_addr == u"Unknown IP Address"

    @pytest.mark.usefixtures(u"clean_db")
    def test_user_objects_in_g_sysadmin(self, app):
        """
        A sysadmin user request will have expected user objects added to
        request.
        """
        user = factories.Sysadmin()
        test_user_obj = model.User.by_name(user[u"name"])

        with app.flask_app.app_context():
            app.get(
                u"/simple_flask",
                extra_environ={u"REMOTE_USER": user[u"name"].encode(u"ascii")},
            )
            assert flask.g.user == user[u"name"]
            assert flask.g.userobj == test_user_obj
            assert flask.g.author == user[u"name"]
            assert flask.g.remote_addr == u"Unknown IP Address"

    def test_user_objects_in_c_normal_user(self, app):
        """
        A normal logged in user request will have expected user objects added
        to request.
        """
        username = factories.User()[u"name"]
        test_user_obj = model.User.by_name(username)

        resp = app.get(
            u"/from_pylons_extension_before_map",
            extra_environ={u"REMOTE_USER": username.encode(u"ascii")},
        )

        # tmpl_context available on response
        assert resp.tmpl_context.user == username
        assert resp.tmpl_context.userobj == test_user_obj
        assert resp.tmpl_context.author == username
        assert resp.tmpl_context.remote_addr == u"Unknown IP Address"

    def test_user_objects_in_c_anon_user(self, app):
        """An anon user request will have expected user objects added to
        request.
        """

        resp = app.get(
            u"/from_pylons_extension_before_map",
            extra_environ={u"REMOTE_USER": str(u"")},
        )

        # tmpl_context available on response
        assert resp.tmpl_context.user == u""
        assert resp.tmpl_context.userobj is None
        assert resp.tmpl_context.author == u"Unknown IP Address"
        assert resp.tmpl_context.remote_addr == u"Unknown IP Address"

    @pytest.mark.usefixtures(u"clean_db")
    def test_user_objects_in_c_sysadmin(self, app):
        """A sysadmin user request will have expected user objects added to
        request.
        """
        username = factories.Sysadmin()[u"name"]
        test_user_obj = model.User.by_name(username)

        resp = app.get(
            u"/from_pylons_extension_before_map",
            extra_environ={u"REMOTE_USER": username.encode(u"ascii")},
        )

        # tmpl_context available on response
        assert resp.tmpl_context.user == username
        assert resp.tmpl_context.userobj == test_user_obj
        assert resp.tmpl_context.author == username
        assert resp.tmpl_context.remote_addr == u"Unknown IP Address"

    @pytest.mark.ckan_config(
        u"ckan.use_pylons_response_cleanup_middleware", True
    )
    def test_pylons_route_with_cleanup_middleware_activated(self, app):
        u"""Test the home page renders with the middleware activated

        We are just testing the home page renders without any troubles and that
        the middleware has not done anything strange to the response string"""

        response = app.get(url=u"/pylons_translated")

        assert response.status_int == 200
        # make sure we haven't overwritten the response too early.
        assert u"cleanup middleware" not in response.body


@pytest.mark.ckan_config(u"SECRET_KEY", u"super_secret_stuff")
def test_secret_key_is_used_if_present(app):
    assert app.flask_app.config[u"SECRET_KEY"] == u"super_secret_stuff"


@pytest.mark.ckan_config(u"SECRET_KEY", None)
def test_beaker_secret_is_used_by_default(app):
    assert (
        app.flask_app.config[u"SECRET_KEY"] == config[u"beaker.session.secret"]
    )


@pytest.mark.ckan_config(u"SECRET_KEY", None)
@pytest.mark.ckan_config(u"beaker.session.secret", None)
def test_no_beaker_secret_crashes(make_app):
    # TODO: When Pylons is finally removed, we should test for
    # RuntimeError instead (thrown on `make_flask_stack`)
    with pytest.raises(RuntimeError):
        make_app()


@pytest.mark.parametrize(
    u"rv,app_base",
    [
        ((False, u"flask_app"), CKANFlask),
        ((True, u"pylons_app", u"core"), CKANPylonsApp),
    ],
)
def test_can_handle_request_with_environ(monkeypatch, app, rv, app_base):
    ckan_app = app.app

    handler = mock.Mock(return_value=rv)
    monkeypatch.setattr(app_base, u"can_handle_request", handler)

    environ = {u"PATH_INFO": str(u"/")}
    wsgiref.util.setup_testing_defaults(environ)
    start_response = mock.MagicMock()
    ckan_app(environ, start_response)

    assert handler.called_with(environ)


def test_ask_around_is_called(monkeypatch, app):
    ask = mock.MagicMock()
    monkeypatch.setattr(AskAppDispatcherMiddleware, u"ask_around", ask)
    app.get(u"/", status=404)
    assert ask.called


def test_ask_around_is_called_with_args(monkeypatch, app):
    ckan_app = app.app

    environ = {}
    start_response = mock.MagicMock()
    wsgiref.util.setup_testing_defaults(environ)

    ask = mock.MagicMock()
    monkeypatch.setattr(AskAppDispatcherMiddleware, u"ask_around", ask)

    ckan_app(environ, start_response)
    assert ask.called
    ask.assert_called_with(environ)


def test_ask_around_flask_core_route_get(app):
    ckan_app = app.app

    environ = {u"PATH_INFO": u"/", u"REQUEST_METHOD": u"GET"}
    wsgiref.util.setup_testing_defaults(environ)

    answers = ckan_app.ask_around(environ)

    assert answers == [(True, u"flask_app", u"core"), (False, u"pylons_app")]


def test_ask_around_flask_core_route_post(app):
    ckan_app = app.app

    environ = {u"PATH_INFO": u"/group/new", u"REQUEST_METHOD": u"POST"}
    wsgiref.util.setup_testing_defaults(environ)

    answers = ckan_app.ask_around(environ)

    # Even though this route is defined in Flask, there is catch all route
    # in Pylons for all requests to point arbitrary urls to templates with
    # the same name, so we get two positive answers
    assert answers == [
        (True, u"flask_app", u"core"),
        (True, u"pylons_app", u"core"),
    ]
