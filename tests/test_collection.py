import re

from pytest import skip # noqa


# For 'testdir' fixture, mostly
pytest_plugins = 'pytester'


class Test_pytest_collect_file(object):
    def test_only_loads_dot_py_files(self, testdir):
        testdir.makepyfile(somefile="""
            def hello_how_are_you():
                pass
        """)
        testdir.makefile('.txt', someotherfile="whatever")
        stdout = testdir.runpytest().stdout.str()
        # TODO: find it hard to believe pytest lacks strong "x in y" string
        # testing, but I cannot find any outside of fnmatch_lines (which is
        # specific to this testdir stuff, and also lacks an opposite...)
        assert "somefile.py" in stdout
        # This wouldn't actually even happen; we'd get an ImportError instead
        # as pytest tries importing 'someotherfile'. But eh.
        assert "whatever.txt" not in stdout

    def test_skips_underscored_files(self, testdir):
        testdir.makepyfile(hastests="""
            from _util import helper

            def hello_how_are_you():
                helper()
        """)
        testdir.makepyfile(_util="""
            def helper():
                pass
        """)
        # TODO: why Result.str() and not str(Result)? Seems unPythonic
        stdout = testdir.runpytest().stdout.str()
        assert "hastests.py" in stdout
        assert "_util.py" not in stdout

    def test_skips_underscored_directories(self, testdir):
        testdir.makepyfile(hello="""
            def hi_im_a_test():
                pass
""")
        # NOTE: this appears to work due to impl details of pytester._makefile;
        # namely that the kwarg keys are handed directly to tmpdir.join(),
        # where tmpdir is a py.path.LocalPath.
        testdir.makepyfile(**{'_nope/yallo': """
            def hi_im_not_a_test():
                pass
"""})
        stdout = testdir.runpytest("-v").stdout.str()
        assert "hi im a test" in stdout
        assert "hi im not a test" not in stdout

    def test_does_not_consume_conftest_files(self, testdir):
        testdir.makepyfile(actual_tests="""
            def hello_how_are_you():
                pass
        """)
        testdir.makepyfile(conftest="""
            def this_does_nothing_useful():
                pass
        """)
        stdout = testdir.runpytest().stdout.str()
        assert "actual_tests.py" in stdout
        assert "conftest.py" not in stdout


class TestRelaxedMixin:
    def test_selects_all_non_underscored_members(self, testdir):
        testdir.makepyfile("""
            def hello_how_are_you():
                pass

            def _help_me_understand():
                pass

            class YupThisIsTests:
                def please_test_me_thx(self):
                    pass

                def _helper_method_hi(self):
                    pass

                class NestedTestClassAhoy:
                    def hello_I_am_a_test_method(self):
                        pass

                    def _but_I_am_not(self):
                        pass

                class _NotSureWhyYouWouldDoThisButWhatever:
                    def this_should_not_appear(self):
                        pass

            class _ForSomeReasonIAmDefinedHereButAmNotATest:
                def usually_you_would_just_import_this_but_okay(self):
                    pass
        """)
        stdout = testdir.runpytest("-v").stdout.str()
        for substring in (
            "hello how are you",
            "please test me thx",
            "hello I am a test method",
        ):
            assert substring in stdout
        for substring in (
            "help me understand",
            "helper method hi",
            "NotSureWhyYouWouldDoThisButWhatever",
            "ForSomeReasonIAmDefinedHereButAmNotATest",
        ):
            assert substring not in stdout

    def test_skips_setup_and_teardown(self, testdir):
        # TODO: probably other special names we're still missing?
        testdir.makepyfile("""
            def setup():
                pass

            def teardown():
                pass

            def actual_test():
                pass

            class Outer:
                def setup(self):
                    pass

                def teardown(self):
                    pass

                def actual_nested_test(self):
                    pass
        """)
        stdout = testdir.runpytest("-v").stdout.str()
        # These skipped. Gotta regex them because the test name includes the
        # words 'setup' and 'teardown', heh.
        assert not re.match(r'^setup$', stdout)
        assert not re.match(r'^teardown$', stdout)
        # Real tests not skipped
        assert "actual test" in stdout
        assert "actual nested test" in stdout


class TestSpecModule:
    def test_skips_non_callable_items(self, testdir):
        testdir.makepyfile("""
            some_uncallable = 17

            def some_callable():
                pass
        """)
        stdout = testdir.runpytest("-v").stdout.str()
        assert "some_uncallable" not in stdout

    def test_skips_imported_objects(self, testdir):
        testdir.makepyfile(_util="""
            def helper():
                pass

            class Helper:
                pass

            class NewHelper(object):
                pass
        """)
        testdir.makepyfile("""
            from _util import helper, Helper, NewHelper

            def a_test():
                pass
        """)
        stdout = testdir.runpytest("-v").stdout.str()
        assert "a test" in stdout
        assert "helper" not in stdout
        assert "Helper" not in stdout
        assert "NewHelper" not in stdout

    def test_does_not_warn_about_imported_names(self, testdir):
        # Trigger is something that appears callable but isn't a real function;
        # almost any callable class seems to suffice. (Real world triggers are
        # things like invoke/fabric Task objects.)
        # Can also be triggered if our collection is buggy and does not
        # explicitly reject imported classes (i.e. if we only reject funcs).
        testdir.makepyfile(_util="""
            class Callable(object):
                def __call__(self):
                    pass

            helper = Callable()

            class HelperClass:
                def __init__(self):
                    pass
        """)
        testdir.makepyfile("""
            from _util import helper, HelperClass

            def a_test():
                pass
        """)
        stdout = testdir.runpytest("-sv").stdout.str()
        # TODO: more flexible test in case text changes? eh.
        for warning in (
            "cannot collect 'helper' because it is not a function",
            "cannot collect test class 'HelperClass'",
        ):
            assert warning not in stdout

    def test_replaces_class_tests_with_custom_recursing_classes(self, testdir):
        testdir.makepyfile("""
            class Outer:
                class Middle:
                    class Inner:
                        def oh_look_an_actual_test(self):
                            pass
        """)
        stdout = testdir.runpytest("-v").stdout.str()
        expected = """
Outer

    Middle

        Inner

            oh look an actual test
""".lstrip()
        assert expected in stdout


class TestSpecInstance:
    def test_methods_self_objects_exhibit_class_attributes(self, testdir):
        # Mostly a sanity test; pytest seems to get out of the way enough that
        # the test is truly a bound method & the 'self' is truly an instance of
        # the class.
        testdir.makepyfile("""
            class MyClass:
                an_attr = 5

                def some_test(self):
                    assert hasattr(self, 'an_attr')
                    assert self.an_attr == 5
        """)
        # TODO: first thought was "why is this not automatic?", then realized
        # "duh, it'd be annoying if you wanted to test failure related behavior
        # a lot"...but still want some slightly nicer helper I think
        assert testdir.runpytest().ret == 0

    def test_nested_self_objects_exhibit_parent_attributes(self, testdir):
        # TODO: really starting to think going back to 'real' fixture files
        # makes more sense; this is all real python code and is eval'd as such,
        # but it is only editable and viewable as a string. No highlighting.
        testdir.makepyfile("""
            class MyClass:
                an_attr = 5

                class Inner:
                    def inner_test(self):
                        assert hasattr(self, 'an_attr')
                        assert self.an_attr == 5
        """)
        assert testdir.runpytest().ret == 0

    def test_nesting_is_infinite(self, testdir):
        testdir.makepyfile("""
            class MyClass:
                an_attr = 5

                class Inner:
                    class Deeper:
                        class EvenDeeper:
                            def innermost_test(self):
                                assert hasattr(self, 'an_attr')
                                assert self.an_attr == 5
        """)
        assert testdir.runpytest().ret == 0

    def test_overriding_works_naturally(self, testdir):
        testdir.makepyfile("""
            class MyClass:
                an_attr = 5

                class Inner:
                    an_attr = 7

                    def inner_test(self):
                        assert self.an_attr == 7
        """)
        assert testdir.runpytest().ret == 0

    def test_methods_from_outer_classes_are_not_copied(self, testdir):
        testdir.makepyfile("""
            class MyClass:
                def outer_test(self):
                    pass

                class Inner:
                    def inner_test(self):
                        assert not hasattr(self, 'outer_test')
        """)
        assert testdir.runpytest().ret == 0

    def test_module_contents_are_not_copied_into_top_level_classes(
        self, testdir
    ):
        testdir.makepyfile("""
            module_constant = 17

            class MyClass:
                def outer_test(self):
                    assert not hasattr(self, 'module_constant')
        """)
        assert testdir.runpytest().ret == 0
