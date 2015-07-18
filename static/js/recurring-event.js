/** Handles the little box for recurring events. */

/** Pseudo-namespace for everything in this file. */
recurringEvents = {};

/** Class for dealing with the recurring events box. */
recurringEvents.dialogBox = function() {
  // The current pane being shown.
  this.currentPane_ = 'monthly';

  // Dropdown menus.
  this.monthNumberDropdown_ = new recurringEvents.dropdown('number-dropdown');
  this.monthDayDropdown_ = new recurringEvents.dropdown('month-day-dropdown');

  /** Registers all event handlers. */
  this.registerHandlers = function() {
    var outer_this = this;

    $('#recurring').click(function(event) {
      if (event.target.checked) {
        outer_this.showDialog_(true);
      } else {
        outer_this.showDialog_(false);
      }
    });
    $('#edit-repeat').click(function(event) {
      event.preventDefault();

      outer_this.showDialog_(true);
    });

    $('#okay-button').click(function(event) {
      outer_this.doOkay_();
    });
    $('#cancel-button').click(function(event) {
      outer_this.doCancel_();
    });

    $('#monthly-pill').click(function() {
      outer_this.showMonthly_();
    });
    $('#weekly-pill').click(function() {
      outer_this.showWeekly_();
    });
    $('#daily-pill').click(function() {
      outer_this.showDaily_();
    });
  };

  /** Shows the repeat event dialog box.
  * @private
  * @param {Boolean} show: Whether to show or hide the dialog.
  */
  this.showDialog_ = function(show) {
    if (show) {
      $('#recurring-modal').modal('show');

      // Show the edit link.
      $('#edit-repeat').show();
    } else {
      $('#recurring-modal').modal('hide');

      // Hide the edit link.
      $('#edit-repeat').hide();
    }
  };

  /** Performs the action when the user clicks the "Ok" button.
  * @private
  */
  this.doOkay_ = function() {
    // Save how many repetitions we want.
    var repetitions = Number($('#repetitions').val());
    // Save whether the weekday only box is checked.
    var weekdaysOnly = document.getElementById('weekdays-only').checked;
    // Construct a dictionary with data about the recurring event.
    var recurringData = {'frequency': this.currentPane_,
                         'repetitions': repetitions,
                         'dayNumber': this.monthNumberDropdown_.getValue(),
                         'monthDay': this.monthDayDropdown_.getValue(),
                         'weekdaysOnly': weekdaysOnly};

    // Save it to the hidden input.
    $('#recurring-data').val(JSON.stringify(recurringData));
  };

  /** Performs the action when the user clicks the "Cancel" button.
  * @private
  */
  this.doCancel_ = function() {
    // Uncheck the repeat box.
    $('#recurring').attr('checked', false);
    // Don't show the edit link.
    $('#edit-repeat').hide();
  };

  /** Shows the montly event pane.
  * @private
  */
  this.showMonthly_ = function() {
    this.doShowPane_('monthly');
  };

  /** Shows the weekly event pane.
  * @private
  */
  this.showWeekly_ = function() {
    this.doShowPane_('weekly');
  };

  /** Shows the daily event pane.
  * @private
  */
  this.showDaily_ = function() {
    this.doShowPane_('daily');
  };

  /** Hides the current pane and shows a new one.
  * @private
  * @param {String} name: The name of the pane to show.
  */
  this.doShowPane_ = function(name) {
    if (this.currentPane_ != name) {
      // Hide the old pane.
      $('#' + this.currentPane_ + '-div').fadeOut(200, function() {
        // Show the new one.
        $('#' + name + '-div').fadeIn(200);
      });

      this.currentPane_ = name;
    }
  };
};

/** Class for handling dropdown menus.
* @constructor
* @param {String} name: The id of the dropdown menu.
*/
recurringEvents.dropdown = function(name) {
  /** Does initialization work.
  * @private
  */
  this.doInit_ = function() {
    // Find the dropdown in question.
    var dropdown = $('#' + this.name_);

    // Find all the options for it.
    var options = dropdown.next();
    var outer_this = this;
    options.children('li').each(function() {
      // Put a click handler on all the list items.
      var element = this;
      $(this).click(function() {
        outer_this.switchMenu_(element);
      });
    });

    // Find the initial value of the dropdown.
    this.value_ = dropdown.text().trim()
  };

  /** Switches the menu selection to a new option.
  * @private
  * @param {Object} element: The element that was selected.
  */
  this.switchMenu_ = function(element) {
    var button = $('#' + this.name_);

    // Get the text of the selected element.
    var text = $(element).text();
    // Set the current value.
    this.value_ = text;

    // Add the little caret thing, and a space to separate it a little.
    text += ' <span class="caret"></span>';
    // Set the button text to it.
    button.html(text);
  };

  /** Gets the current option selected.
  * @returns: The current option selected.
  */
  this.getValue = function() {
    return this.value_;
  };

  this.name_ = name;
  this.doInit_();
};

$(document).ready(function() {
  box = new recurringEvents.dialogBox();
  box.registerHandlers();
});
